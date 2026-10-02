package org.freezingsaddles.cdk

import software.amazon.awscdk.{CfnOutput, Duration, RemovalPolicy, Stack, StackProps}
import software.amazon.awscdk.customresources.{
  AwsCustomResource,
  AwsCustomResourcePolicy,
  AwsSdkCall,
  PhysicalResourceId,
}
import software.amazon.awscdk.services.ec2.{
  GatewayVpcEndpointAwsService,
  InterfaceVpcEndpointAwsService,
  Port,
  SecurityGroup,
  SubnetSelection,
  Vpc,
  VpcLookupOptions,
}
import software.amazon.awscdk.services.iam.{Effect, PolicyStatement}
import software.amazon.awscdk.services.lambda.{Code, Function, Runtime}
import software.amazon.awscdk.services.logs.{LogGroup, RetentionDays}
import software.amazon.awscdk.services.route53.{
  CnameRecord,
  MxRecord,
  MxRecordValue,
  PublicHostedZone,
  PublicHostedZoneAttributes,
}
import software.amazon.awscdk.services.s3.{
  BlockPublicAccess,
  Bucket,
  BucketEncryption,
  LifecycleRule,
}
import software.amazon.awscdk.services.ses.{
  EmailIdentity,
  Identity,
  IReceiptRuleAction,
  ReceiptRuleOptions,
  ReceiptRuleSet,
}
import scala.jdk.CollectionConverters.*
import software.amazon.awscdk.services.ses.actions.{Lambda as LambdaAction, S3 as S3Action}
import software.constructs.Construct

/** Receives the WordPress registration confirmation email and records it in the database.
  *
  * Mail for the recipient address lands at SES (the MX record on its domain points there), which
  * writes the raw message to the bucket and invokes the function; the function parses the form
  * table out of the HTML and inserts a `registrations` row.
  *
  * Context (cdk.json or -c):
  *   - hostedZoneId, zoneName: the Route 53 zone for freezingsaddles.org, in this account. Given as
  *     attributes rather than looked up so `cdk synth` works without credentials.
  *   - recipient (default register@inbox.freezingsaddles.org): the address to receive on. Its
  *     domain becomes an SES identity with DKIM records and the MX record in the zone.
  *   - dbHost, dbUser (required), dbPort (default 3306), dbName (default freezing): the MySQL
  *     connection, for a user that can insert into `registrations` and select from `athletes`.
  *     Plain environment variables, like the config file the Python apps read.
  *   - dbPassword or dbPasswordParam: that user's password, one of two ways. dbPassword puts it
  *     straight into the function's environment: encrypted at rest, readable by anyone who can read
  *     the function's configuration, the same trust as the .env file the Python apps use on the
  *     host, and free. dbPasswordParam (default /freezing/registration/db-password when neither is
  *     given) names an SSM SecureString the function reads at runtime; create it by hand, since
  *     CloudFormation cannot. Inside a VPC that read needs an SSM interface endpoint, which is
  *     billed hourly, so a private database wants dbPassword.
  *   - vpcId, dbSecurityGroupId (optional, together): run the function inside the database's VPC.
  *     The stack makes the function its own security group and adds an ingress rule for it to the
  *     database's group on the database port, adds a free S3 gateway endpoint so the function can
  *     fetch the mail without a NAT, and adds the SSM endpoint only if the password comes from SSM.
  *     The function lands in the VPC's private subnets when it has them, public ones otherwise; it
  *     gets no public address either way and needs none. Without these the function runs outside
  *     any VPC and the database must be publicly reachable.
  *   - activateRuleSet (default true): make this the account's active receipt rule set. An account
  *     has one; set this false if another stack already owns it and add the rule there.
  */
class RegistrationStack(scope: Construct, id: String, props: StackProps)
    extends Stack(scope, id, props):

  private def context(name: String): Option[String] =
    Option(getNode.tryGetContext(name)).map(_.toString).filter(_.nonEmpty)
  private def required(name: String): String        =
    context(name).getOrElse(sys.error(s"$name context is required"))

  locally:
    val recipient       = context("recipient").getOrElse("register@inbox.freezingsaddles.org")
    val mailDomain      = recipient.substring(recipient.indexOf('@') + 1)
    val dbHost          = required("dbHost")
    val dbUser          = required("dbUser")
    val dbPort          = context("dbPort").getOrElse("3306")
    val dbName          = context("dbName").getOrElse("freezing")
    val dbPassword      = context("dbPassword")
    val dbPasswordParam = dbPassword match
      case Some(_) => None
      case None    => Some(context("dbPasswordParam").getOrElse("/freezing/registration/db-password"))
    val zone            = PublicHostedZone.fromPublicHostedZoneAttributes(
      this,
      "Zone",
      PublicHostedZoneAttributes
        .builder()
        .hostedZoneId(required("hostedZoneId"))
        .zoneName(required("zoneName"))
        .build(),
    )

    // The identity is the mail subdomain, not the zone's apex: the apex may already be verified
    // for something else, and this stack should own only its own records. Verifying by domain
    // name leaves the DKIM CNAMEs to us.
    val identity = EmailIdentity.Builder
      .create(this, "Identity")
      .identity(Identity.domain(mailDomain))
      .build()
    for (record, i) <- identity.getDkimRecords.asScala.zipWithIndex do
      CnameRecord.Builder
        .create(this, s"Dkim$i")
        .zone(zone)
        .recordName(record.getName)
        .domainName(record.getValue)
        .ttl(Duration.minutes(30))
        .build()
    MxRecord.Builder
      .create(this, "InboundMx")
      .zone(zone)
      .recordName(mailDomain)
      .values(
        jList(
          MxRecordValue
            .builder()
            .priority(10)
            .hostName(s"inbound-smtp.${getRegion}.amazonaws.com")
            .build()
        )
      )
      .ttl(Duration.minutes(30))
      .build()

    // Every message is kept for a while: the row is derived from it, so a parser bug or a form
    // change can be replayed from here rather than asking people to register again.
    val bucket = Bucket.Builder
      .create(this, "Mail")
      .blockPublicAccess(BlockPublicAccess.BLOCK_ALL)
      .encryption(BucketEncryption.S3_MANAGED)
      .enforceSsl(true)
      .lifecycleRules(jList(LifecycleRule.builder().expiration(Duration.days(400)).build()))
      .removalPolicy(RemovalPolicy.RETAIN)
      .build()
    val prefix = "inbound/"

    val vpc = for vpcId <- context("vpcId"); dbSgId <- context("dbSecurityGroupId")
    yield
      val v  = Vpc.fromLookup(this, "Vpc", VpcLookupOptions.builder().vpcId(vpcId).build())
      val sg = SecurityGroup.Builder
        .create(this, "ReceiveSg")
        .vpc(v)
        .description("registration receiver")
        .allowAllOutbound(true)
        .build()
      SecurityGroup
        .fromSecurityGroupId(this, "DbSg", dbSgId)
        .addIngressRule(sg, Port.tcp(dbPort.toInt), "registration receiver")
      v.addGatewayEndpoint(
        "S3Endpoint",
        software.amazon.awscdk.services.ec2.GatewayVpcEndpointOptions
          .builder()
          .service(GatewayVpcEndpointAwsService.S3)
          .build(),
      )
      if dbPasswordParam.isDefined then
        v.addInterfaceEndpoint(
          "SsmEndpoint",
          software.amazon.awscdk.services.ec2.InterfaceVpcEndpointOptions
            .builder()
            .service(InterfaceVpcEndpointAwsService.SSM)
            .build(),
        )
      (v, sg)

    val fnBuilder = Function.Builder
      .create(this, "Receive")
      .runtime(Runtime.JAVA_21)
      .code(Code.fromAsset("../target/out/jvm/scala-3.9.0/registration/registration.jar"))
      .handler("org.freezingsaddles.registration.Lambda::handleRequest")
      .memorySize(1024)
      .timeout(Duration.minutes(1))
      .environment(
        jMap(
          (List(
            "BUCKET"        -> bucket.getBucketName,
            "OBJECT_PREFIX" -> prefix,
            "DB_HOST"       -> dbHost,
            "DB_PORT"       -> dbPort,
            "DB_NAME"       -> dbName,
            "DB_USER"       -> dbUser,
          ) ++ dbPassword.map("DB_PASSWORD" -> _)
            ++ dbPasswordParam.map("DB_PASSWORD_PARAM" -> _))*
        )
      )
      // An explicit group, because the one the runtime would create keeps logs for ever.
      .logGroup(
        LogGroup.Builder.create(this, "ReceiveLogs").retention(RetentionDays.ONE_MONTH).build()
      )
    // CDK's default picks only subnets with a NAT route and refuses isolated ones, which is what
    // a VPC's "private" subnets usually are when nothing in them needs the internet. Take
    // whatever the VPC has, in order of preference; the function needs no route out either way.
    vpc.foreach: (v, sg) =>
      val subnets = List(v.getPrivateSubnets, v.getIsolatedSubnets, v.getPublicSubnets)
        .map(_.asScala.toList)
        .find(_.nonEmpty)
        .getOrElse(sys.error(s"VPC ${v.getVpcId} has no subnets"))
      fnBuilder
        .vpc(v)
        .vpcSubnets(SubnetSelection.builder().subnets(subnets.asJava).build())
        .allowPublicSubnet(true)
        .securityGroups(jList(sg))
    val fn        = fnBuilder.build()
    bucket.grantRead(fn, prefix + "*")
    // Reading a SecureString under the default aws/ssm key needs no kms:Decrypt: that key is
    // open to the account's own principals. A customer-managed key would need the grant.
    dbPasswordParam.foreach: param =>
      fn.addToRolePolicy(
        PolicyStatement.Builder
          .create()
          .actions(jList("ssm:GetParameter"))
          .resources(jList(s"arn:aws:ssm:${getRegion}:${getAccount}:parameter$param"))
          .build()
      )
    // Reading a SecureString under the default aws/ssm key needs no kms:Decrypt: that key is
    // open to the account's own principals. A customer-managed key would need the grant.
    // Store first, then invoke: the function reads the object the S3 action just wrote.
    val ruleSet   = ReceiptRuleSet.Builder
      .create(this, "RuleSet")
      .rules(
        jList(
          ReceiptRuleOptions
            .builder()
            .enabled(true)
            .recipients(jList(recipient))
            .scanEnabled(true)
            .actions(
              jList[IReceiptRuleAction](
                S3Action.Builder.create().bucket(bucket).objectKeyPrefix(prefix).build(),
                LambdaAction.Builder.create().function(fn).build(),
              )
            )
            .build()
        )
      )
      .build()

    // CloudFormation can create a rule set but not make it the active one; SES receives nothing
    // until something calls SetActiveReceiptRuleSet.
    if context("activateRuleSet").forall(_ != "false") then
      val activate = AwsCustomResource.Builder
        .create(this, "ActivateRuleSet")
        .installLatestAwsSdk(false)
        .onCreate(
          AwsSdkCall
            .builder()
            .service("SES")
            .action("setActiveReceiptRuleSet")
            .parameters(jMap[Object]("RuleSetName" -> ruleSet.getReceiptRuleSetName))
            .physicalResourceId(PhysicalResourceId.of("activate-rule-set"))
            .build()
        )
        .onDelete(
          AwsSdkCall
            .builder()
            .service("SES")
            .action("setActiveReceiptRuleSet")
            .parameters(jMap[Object]())
            .physicalResourceId(PhysicalResourceId.of("deactivate-rule-set"))
            .build()
        )
        .policy(
          AwsCustomResourcePolicy.fromStatements(
            jList(
              PolicyStatement.Builder
                .create()
                .effect(Effect.ALLOW)
                .actions(jList("ses:SetActiveReceiptRuleSet"))
                .resources(jList("*"))
                .build()
            )
          )
        )
        .build()
      activate.getNode.addDependency(ruleSet)
    end if

    CfnOutput.Builder.create(this, "Recipient").value(recipient).build()
    CfnOutput.Builder.create(this, "MailBucket").value(bucket.getBucketName).build()
    CfnOutput.Builder.create(this, "ReceiveFunction").value(fn.getFunctionName).build()
end RegistrationStack
