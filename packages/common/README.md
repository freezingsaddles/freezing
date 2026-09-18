# freezing-common

Code shared by the Freezing Saddles apps that is not part of the data model
(`freezing-model`): business rules that both `freezing-web` and
`freezing-sync` need, such as registering a Strava athlete and matching
their clubs to the competition's teams.

Everything here takes its configuration as arguments. The apps bind their own
settings when they call in, so this package has no config of its own.
