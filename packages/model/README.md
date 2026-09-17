# freezing-model

SQLAlchemy model for the Freezing Saddles database.

This package uses [SQLAlchemy](https://www.sqlalchemy.org/) to model the
database tables for the Freezing Saddles database. It uses
[alembic](https://pypi.org/project/alembic/) to perform database migrations.

## Usage

This is a workspace member used by the apps in this repository:
[web](../../apps/web), [sync](../../apps/sync) and [nq](../../apps/nq).
There is no separate release; a change to the model and the app code that
uses it land in the same pull request.

When used from `freezing-web` it will retrieve its database configuration
from the [Flask](http://flask.pocoo.org/) application configuration. When
used from the command line, it will take its configuration from the
[alembic.ini](alembic.ini) file and optionally from the environment.

You can override the database URL by specifying a `SQLALCHEMY_URL` environment
variable, for example:

    cd packages/model
    export SQLALCHEMY_URL='mysql+pymysql://user:password@127.0.0.1/freezing?charset=utf8mb4&binary_prefix=true'
    uv run alembic current
    uv run alembic upgrade head

## Developing

Install, lint and format from the repository root as described in the
[top-level README](../../README.md); there is nothing package-specific to set
up. The commands below assume you are in `packages/model`, where
`alembic.ini` lives.

## Altering the schema

Alter `orm.py` to add your new tables or fields to the ORM. This will be used when initializing a database from scratch.

Create a migration script:

    uv run alembic revision -m "description of change"

Edit the resulting migration script to upgrade and downgrade.

Check your current version:

    uv run alembic current

Apply the changes:

    uv run alembic upgrade head

Check your table with mysql:

    mysql -u freezing -p -D freezing
    mysql> show columns from some_table;

Unapply the changes using the version from the current command:

    uv run alembic downgrade <version>

You can then re-upgrade and be done.

## Useful Queries

(TODO: This is probably not the best place for this documentation, but I'm not sure where else to put it)

Beyond the model definitions there are a few other useful SQL utilities and queries that can help in operations:

The script [bin/registrants.py](bin/registrants.py), given a CSV export from the WordPress registration site for Freezing Saddles, can generate a `registrants` table in the `freezing` database that is useful for determining who has registered but has not authorized properly in the database.

These queries can find users who still need to authorize with Strava and generate a list of emails for those users:

```
select regnum, id, username, name, email, registered_on from registrants r where id not in (select id from athletes); /* Athletes who have never authorized with the freezingsaddles.org site */

select r.regnum, a.id, r.username, r.name, r.email, r.registered_on from registrants r inner join athletes a on (r.id = a.id) where a.team_id is null; /* Athletes that need to re-authorize because we can't read their teams */

select email from registrants where id not in (select id from athletes) union select r.email from registrants r inner join athletes a on (r.id = a.id) where a.team_id is null; /* Emails of users from both of the above groups who need to authorize in Strava */
```
