# Build from the workspace root: docker build -f apps/freezebot/Dockerfile .
FROM eclipse-temurin:21-jdk AS build
# The sbt runner script; the sbt version the build wants comes from project/build.properties.
ARG SBT_VERSION=2.0.9
RUN curl -fsSL "https://github.com/sbt/sbt/releases/download/v${SBT_VERSION}/sbt-${SBT_VERSION}.tgz" | tar xz -C /opt
ENV PATH="/opt/sbt/bin:$PATH"
WORKDIR /build

# Resolve through a mirror, and only through it: repo1.maven.org rate-limits a
# runner sharing an address with the rest of GitHub, and has failed this build.
COPY apps/freezebot/repositories /root/.sbt/repositories
ENV SBT_OPTS="-Dsbt.override.build.repos=true"

# The build definition first, so sbt and the dependencies cache independently of source changes.
COPY apps/freezebot/build.sbt ./
COPY apps/freezebot/project/build.properties apps/freezebot/project/plugins.sbt project/
RUN sbt --batch update

COPY apps/freezebot ./
RUN sbt --batch assembly

# A runtime of just the modules the jar uses (jdeps --print-module-deps, plus the EC crypto the
# TLS handshakes want on 21), a third the size of a full JRE image.
RUN jlink --add-modules java.base,java.management,java.naming,java.net.http,java.security.sasl,java.sql,jdk.unsupported,jdk.crypto.ec \
      --strip-debug --no-man-pages --no-header-files --compress zip-6 --output /jre

FROM debian:bookworm-slim
RUN addgroup --system freezing && adduser --system --ingroup freezing freezing
COPY --from=build /jre /jre
COPY --from=build /build/target/out/jvm/scala-3.9.0/freezebot/freezebot.jar /app/freezebot.jar
# The tag to channel mapping is the web app's, so a channel is configured once.
COPY apps/web/leaderboards/hashtag.yml /data/leaderboards/hashtag.yml
ENV FREEZEBOT_TAGS_FILE=/data/leaderboards/hashtag.yml
USER freezing
# A small heap, the serial collector and the quick compiler only: the host is small and the bot
# mostly sleeps. Idle it sits around 85 MB resident, against 125 MB with the defaults.
CMD ["/jre/bin/java", "-Xmx32m", "-Xss512k", "-XX:+UseSerialGC", "-XX:TieredStopAtLevel=1", "-XX:ReservedCodeCacheSize=16m", "-jar", "/app/freezebot.jar"]
