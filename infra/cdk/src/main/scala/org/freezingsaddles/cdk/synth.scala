package org.freezingsaddles.cdk

import software.amazon.awscdk.{App, Environment, StackProps}

@main def synth(): Unit =
  val app = App()
  val env = Environment
    .builder()
    .account(sys.env.get("CDK_DEFAULT_ACCOUNT").orNull)
    .region(sys.env.get("CDK_DEFAULT_REGION").orNull)
    .build()
  RegistrationStack(app, "FreezingRegistration", StackProps.builder().env(env).build())
  app.synth()
  ()
