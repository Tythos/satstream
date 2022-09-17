SatStream
=========

SatStream is a containerized service for maintaining a modest public satellite
catalog API that supports streaming (e.g., WebSocket) events for on-change
messages. It is largely based on intermediate polls against the CelesTrack
catalog (with environmental controls to respect connection rate limits).

To Build::

  > docker build -t satstream:latest .

To Run::

  > docker run -it -p=8000:8000 satstream:latest

Once running, there are several endpoints that are useful for testing:

* GET "/satcat.csv" will return a direct dump of the latest satellite catalog table

* GET "/" will return a JSON array of all SSCIDs for which elements exist in the datastore

* GET "/<int:sscid>" will return the TLE for that satellite (or 404 if the elements do not exist in the datastore)

* GET "/test" will return an HTML page that includes some basic WebSocket subscription inspection/debugging statements that populate table contents

* WS "/" will subscribe to all future on-change events (including new elements) for all entities

There are several other debugging endpoints but you should not need to use these directly:

* GET "/sockets" will return the number of active WebSocket connections

* POST "/<int:sscid>" will "force" an update of the given entity

Out of respect for Dr. T. S. Kelso, who runs CelesTrack as a non-profit, please do not adjust the "poll" intervals below reasonable revisit rates.

  http://celestrak.org/
