lazy val cdkVersion        = "2.264.0"
lazy val constructsVersion = "10.8.1"

lazy val cdk = project
  .in(file("."))
  .settings(
    name                := "registration-cdk",
    scalaVersion        := "3.9.0",
    scalacOptions ++= Seq("-deprecation", "-feature", "-Wunused:imports"),
    libraryDependencies ++= Seq(
      "software.amazon.awscdk" % "aws-cdk-lib" % cdkVersion,
      "software.constructs"    % "constructs"  % constructsVersion,
    ),
    run / baseDirectory := file(".").getAbsoluteFile,
    run / fork          := true,
    // One formatting config for both builds.
    scalafmtConfig      := file("../.scalafmt.conf"),
  )

addCommandAlias("synth", "runMain org.freezingsaddles.cdk.synth")
