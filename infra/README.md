# Registration receiver

Registration for Freezing Saddles ends on a WordPress site whose form emails a
confirmation to the registrant and to `register@inbox.freezingsaddles.org`.
This receives that copy through Amazon SES, reads the form's answers out of the
HTML and records them in the `registrations` table of the main database, so
the people running the competition can see who registered without reading a
mailbox.

Two sbt builds, Scala 3:

| Path | What it is |
| --- | --- |
| `.` | the Lambda: MIME parsing, form parsing, one row through Magnum |
| `cdk/` | the AWS CDK app that deploys it |

## How it works

1. An MX record on `inbox.freezingsaddles.org` points at SES inbound. Mail
   gets its own subdomain because `register.freezingsaddles.org` is the
   registration website.
2. An SES receipt rule for the recipient writes the raw message to an S3
   bucket and invokes the Lambda with the message id.
3. The Lambda ignores anything whose subject lacks the subject secret
   (`INFRA_SUBJECT_SECRET`), since anyone can mail the address, and ignores
   everything while none is set. The registrant's own confirmation must not
   carry it, so the form needs a separate email action to this address whose
   subject has the secret in it.
4. It fetches the message, walks its MIME parts to the HTML one, and
   reads the two-column table of label and answer. Only these are kept:
   first name, last name, zip code, e-mail, Strava user ID, and the team
   captain answer (blank or `Yes`).
5. It keeps one row per athlete, keyed on the Strava id they typed: their
   latest submission, with `source` saying which email it came from.
   WordPress keeps the history. A submission older than the row is ignored,
   and one with the same answers changes nothing, so a redelivery or a retry
   is harmless. The form comes after connecting Strava, so an id with no
   `athletes` row is a typo, and is logged instead of stored.

## Backfilling from an export

Registrations that arrived while no email reached the receiver can be mailed
in as the form's submissions export: attach the CSV that WordPress exports
to a message to the same address, with the subject secret in its subject
like any other mail. Each row goes through the same rules as an
email, with `form-submission:<#>` as its source and its date read in the
site's Eastern time, so mailing the same export again changes nothing. The
log line counts the rows recorded, updated, unchanged, older and with an
unknown athlete, and names the rows it couldn't read. To check an export
first, save the message as `.eml` and run `sbt "runMain
org.freezingsaddles.registration.preview <file>"`.

Anything that is not a registration confirmation is logged and ignored, but a
CSV attachment that is not an export fails, since whoever sent it meant it. A
message the Lambda cannot store fails the invocation so Lambda retries; the
S3 copy is kept for a year regardless, which is what makes a parser fix
replayable.

The table is created by the Python side: the `Registration` model and its
alembic migration live in [packages/model](../packages/model). Run that
migration before the first deploy.

The database layer is [Magnum](https://github.com/AugustNagro/magnum): the
`Registration` case class is the row, a derived repository does the insert or
update, and the same repositories are there for the next Lambda that reads
more than it writes. No effect system; Magnum runs on plain JDBC.

## Developing

    cd infra
    sbt test                                   # no AWS needed; the repository tests run on in-process H2
    sbt "runMain org.freezingsaddles.registration.preview path/to/message.eml"
    sbt assembly                               # the Lambda jar the CDK app deploys

The preview prints what would be stored for a saved `.eml`, which is the way
to check a new form layout against the parser.

Formatting is `scalafmt` in both builds (`sbt scalafmtAll`); the config is
[.scalafmt.conf](.scalafmt.conf).

## Deploying

Pushes to `main` that touch `infra/` deploy through
[infra-deploy.yml](../.github/workflows/infra-deploy.yml): build the jar, assume
an AWS role over OIDC, `cdk deploy`. Configuration is repository variables and
one secret in the `production` environment:

| Name | Value |
| --- | --- |
| `INFRA_DEPLOY_ROLE_ARN` | the IAM role below |
| `INFRA_HOSTED_ZONE_ID`, `INFRA_ZONE_NAME` | `Z2KDHVD1WMJEDS`, `freezingsaddles.org` |
| `INFRA_RECIPIENT` | `register@inbox.freezingsaddles.org` |
| `INFRA_DB_HOST`, `INFRA_DB_PORT`, `INFRA_DB_NAME`, `INFRA_DB_USER` | the RDS endpoint, `3306`, `freezing`, `freezing` |
| `INFRA_VPC_ID`, `INFRA_DB_SECURITY_GROUP_ID` | `vpc-fb440f81` and the group on the RDS instance |
| `INFRA_DB_PASSWORD` (secret, `production` environment) | the `freezing` user's password |
| `INFRA_SUBJECT_SECRET` (secret, `production` environment) | a phrase the subject of every mail must contain to be read |

The password goes straight into the function's environment: encrypted at rest,
visible only to people who can read the function's configuration, the same
trust as the `.env` on the host, and free. The stack also accepts
`-c dbPasswordParam=...` naming an SSM SecureString instead, which keeps it out
of the environment but inside a VPC needs an SSM interface endpoint that is
billed hourly.

One-time setup in the account:

- `cdk bootstrap aws://299196842131/us-east-1`, once, from anywhere with
  admin credentials.
- An IAM role for GitHub with this trust policy subject (the ids are the
  org's and the repo's, so renames do not break it):

      repo:freezingsaddles@35430981/freezing@1373805993:ref:refs/heads/main

  against the account's `token.actions.githubusercontent.com` OIDC provider,
  and this permission policy, which is all a CDK deploy needs because the
  bootstrap roles do the work:

      {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "sts:AssumeRole",
         "Resource": "arn:aws:iam::299196842131:role/cdk-hnb659fds-*-role-299196842131-us-east-1"},
        {"Effect": "Allow", "Action": "ssm:GetParameter",
         "Resource": "arn:aws:ssm:us-east-1:299196842131:parameter/cdk-bootstrap/hnb659fds/version"}
      ]}

- Point the WordPress form's admin copy at `register@inbox.freezingsaddles.org`
  once the stack is up; nothing arrives before the MX record exists.

The stack verifies `inbox.freezingsaddles.org` as an SES identity (DKIM
records in the zone), adds the MX record, runs the function inside the VPC in
its own security group with an ingress rule on the database's group, adds the
free S3 gateway endpoint the function needs to fetch the mail, and makes its
receipt rule set the account's active one. An account has a single active rule
set; if another stack already owns it, add `-c activateRuleSet=false` to the
deploy and put the rule there.

To deploy by hand instead, with credentials for the account:

    cd infra && sbt assembly
    cd cdk && npm ci
    npx cdk deploy -c hostedZoneId=Z2KDHVD1WMJEDS -c zoneName=freezingsaddles.org \
      -c dbHost=unmanaged-fs-02.c7hti2ehau6i.us-east-1.rds.amazonaws.com -c dbUser=freezing \
      -c dbPassword='...' -c vpcId=vpc-fb440f81 -c dbSecurityGroupId=sg-...

Pull requests that touch `infra/` build, test and synth with placeholder
context but do not deploy.
