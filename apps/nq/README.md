# Freezing Saddles Enqueue

This component is part of the [Freezing Saddles](http://freezingsaddles.com) project.  Its purpose is to receive [webhook activity events from Strava](http://strava.github.io/api/partner/v3/events/) and queue them up for processing.

## Developing

Install from the repository root as described in the
[top-level README](../../README.md), then run the tests from this directory:

```
cd apps/nq
uv run pytest
```

## Deploying with Docker

The image is built from the repository root with
`docker build -f apps/nq/Dockerfile .`. See [deploy](../../deploy) for the
production compose setup this runs in alongside the related containers.

It is designed to run as a container and should be configured with environment variables for:
- `BEANSTALKD_HOST`: The hostname (probably a container link) to a beanstalkd server.
- `BEANSTALKD_PORT`: The port for beanstalkd server (default 11300)
- `STRAVA_VERIFY_TOKEN`: The token to use when verifying the Strava challenge response (must match token used to register subscription).

# Legal

This software is a community-driven effort, and as such the contributions are owned by the individual contributors:

Copyright 2018 Hans Lellelid <br>
Copyright 2020 Richard Bullington-McGuire <br>

This software is licensed under the [Apache 2.0 license](../../LICENSE).
