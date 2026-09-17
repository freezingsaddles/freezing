# Registration receiver

Registration for Freezing Saddles ends on a WordPress site whose form emails a
confirmation to the registrant and to `admin@register.freezingsaddles.org`.
This receives that copy through Amazon SES, reads the form's answers out of the
HTML and records them in the `registrations` table of the main database, so
the people running the competition can see who registered without reading a
mailbox.

Two sbt builds, Scala 3:

| Path | What it is |
| --- | --- |
| `.` | the Lambda: MIME parsing, form parsing, one JDBC insert |
| `cdk/` | the AWS CDK app that deploys it |

## How it works

1. An MX record on `register.freezingsaddles.org` points at SES inbound.
2. An SES receipt rule for the recipient writes the raw message to an S3
   bucket and invokes the Lambda with the message id.
3. The Lambda fetches the message, walks its MIME parts to the HTML one, and
   reads the two-column table of label and answer. Only these are kept:
   first name, last name, zip code, e-mail, Strava user ID, previous year's
   mileage, and the team captain answer (blank or `Yes`).
4. It upserts a row keyed on the email's `Message-Id`, so a redelivery or a
   retry refreshes the row instead of duplicating it. `athlete_id` is set only
   when an `athletes` row with that Strava id already exists; the raw value is
   kept in `strava_id` either way.

Anything that is not a registration confirmation is logged and ignored. A
message the Lambda cannot store fails the invocation so Lambda retries; the
S3 copy is kept for a year regardless, which is what makes a parser fix
replayable.

The table is created by the Python side: the `Registration` model and its
alembic migration live in [packages/model](../packages/model). Run that
migration before the first deploy.

Plain JDBC rather than an effect system: one insert per email is not worth a
connection pool, and every dependency is paid for again at each cold start.

## Developing

    cd infra
    sbt test                                   # unit tests, no AWS or database needed
    sbt "runMain org.freezingsaddles.registration.preview path/to/message.eml"
    sbt assembly                               # the Lambda jar the CDK app deploys

The preview prints what would be stored for a saved `.eml`, which is the way
to check a new form layout against the parser.

Formatting is `scalafmt` in both builds (`sbt scalafmtAll`); the config is
[.scalafmt.conf](.scalafmt.conf).

## Deploying

Before the first deploy, by hand:

- A MySQL user that can insert into `registrations` and select from
  `athletes`, and its password in an SSM SecureString parameter (standard
  parameters are free; CloudFormation cannot create a SecureString itself):

      aws ssm put-parameter --name /freezing/registration/db-password \
        --type SecureString --value '...'

  The host, port, database and user name are ordinary environment variables
  set from CDK context, the same values the Python apps read from their
  config file.

- Reachability. The production database is private, in `vpc-fb440f81`, so pass
  `-c vpcId=vpc-fb440f81` and `-c dbSecurityGroupId=sg-...` (the group on the
  RDS instance). The stack runs the function inside that VPC in its own
  security group, adds the ingress rule for it to the database's group, and
  adds the free S3 gateway endpoint it needs to fetch the mail. Without these
  the function runs outside any VPC, which only works for a publicly reachable
  database.

Then, with credentials for the account that holds the Route 53 zone and the
database:

    cd infra && sbt assembly
    cd cdk && npm ci
    npx cdk deploy \
      -c hostedZoneId=Z... -c zoneName=freezingsaddles.org \
      -c dbHost=unmanaged-fs-02.....rds.amazonaws.com -c dbUser=freezing

The stack verifies `register.freezingsaddles.org` as an SES identity (DKIM
records in the zone), adds the MX record, and makes its receipt rule set the
account's active one. An account has a single active rule set; if another
stack already owns it, pass `-c activateRuleSet=false` and add the rule there.

CI builds, tests and synths on every pull request that touches `infra/`, but
does not deploy; that is a manual step until an OIDC role exists for it.
