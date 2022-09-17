"""
Maintains and automatically updates a "streaming" satellite catalog.
"""

# core modules
import os
import re
import csv
import time
import json
import random
import difflib
import datetime
import threading

# dependencies
import flask
import flask_sockets
import requests
from gevent import pywsgi
from geventwebsocket import handler

# env parameters
SATCAT_POLL_INTERVAL_S = int(os.getenv("SATCAT_POLL_INTERVAL_S", 60 * 60 * 12)) # twice a day by default
SATCAT_POLL_URL = os.getenv("SATCAT_POLL_URL", "https://celestrak.org/pub/satcat.csv")
TLE_POLL_INTERVAL_S = int(os.getenv("TLE_POLL_INTERVAL_S", 10)) # new TLE retrieved every minute, by default
TLE_POLL_URL = os.getenv("TLE_POLL_URL", "https://celestrak.org/NORAD/elements/gp.php?CATNR=%u")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# module-level variables
PACKAGE_PATH, _ = os.path.split(os.path.abspath(__file__))
_, PACKAGE_NAME = os.path.split(PACKAGE_PATH)
APP = flask.Flask(PACKAGE_NAME)
SOCKETS = flask_sockets.Sockets(APP)
WS_POOL = []

def drawSSCID(satCatPath):
    """
    Chooses a SSCID from the satcat atble, based on random selection from
    objects that have not decayed.
    """
    with open(satCatPath, 'r') as f:
        dr = csv.DictReader(f)
        rows = [row for row in dr]
    alive = [row for row in rows if row["DECAY_DATE"] == ""]
    draw = random.choice(alive)
    return int(draw["NORAD_CAT_ID"])

def broadcastChange(sscid, newTle):
    """
    Defines broadcast behavior for entity on-change events.
    """
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    message = json.dumps({
        "id": sscid,
        "timestamp": now.isoformat(),
        "payload": {
            "lines": [line.decode() for line in newTle]
        }
    })
    for ws in WS_POOL:
        if not ws.closed:
            ws.send(message)

@SOCKETS.route("/")
def subscription(ws):
    """
    Endpoint for WebSocket connections. Upon a successful connection, the
    WebSocket is added to a pool and kept open. Any subsequent events will be
    broadcast to this pool.
    """
    global WS_POOL
    WS_POOL.append(ws)
    while not ws.closed:
        _ = ws.receive() # BLOCKING
        time.sleep(1)
    WS_POOL.remove(ws)

@APP.route("/sockets")
def sockets():
    """
    Test endpoint for determining, at runtime, how many WebSocket connections
    are open.
    """
    return str(len(WS_POOL)), 200, {
        "Content-Type": "text/plain"
    }

@APP.route("/test")
def test():
    """
    Returns the "test.html" file to support inspection of entity traffic.
    """
    return flask.send_file(PACKAGE_PATH + "/test.html")

@APP.route("/<int:sscid>", methods=["GET"])
def tle(sscid):
    tlePath = PACKAGE_PATH + "/datastore/%u.tle" % sscid
    if os.path.isfile(tlePath):
        return flask.send_file(tlePath, mimetype="text/plain")
    return "Not Found", 404, {
        "Content-Type": "text/plain"
    }

@APP.route("/")
def index():
    """
    Returns list of all IDs for records in this datastore
    """
    tleFiles = [f for f in os.listdir(PACKAGE_PATH + "/datastore") if f.endswith(".tle")]
    sscids = [int(re.sub("\.tle$", "", tf)) for tf in tleFiles]
    sscids.sort()
    return json.dumps(sscids), 200, {
        "Content-Type": "application/json"
    }

@APP.route("/<int:sscid>", methods=["POST"])
def poke(sscid):
    """
    'Forces' update of a specific TLE, which is both stashed and returned.
    """
    res = requests.get(TLE_POLL_URL % sscid)
    tlePath = PACKAGE_PATH + "/datastore/%u.tle" % sscid
    with open(tlePath, 'wb') as f:
        f.write(res.content)
    return res.content, 200, {
        "Content-Type": "text/plain"
    }

@APP.route("/satcat.csv")
def satcat():
    """
    Returns the latest satcat directly from the datastore's .CSV file.
    """
    satcatPath = PACKAGE_PATH + "/datastore/satcat.csv"
    return flask.send_file(satcatPath)

def startSatcatPoll():
    """
    Starts an intermediate poll (defaults to once every 12 hours) against the
    satellite catalog table (.CSV).
    """
    print("Starting satcat poll against %s..." % SATCAT_POLL_URL)
    exitCondition = threading.Event()
    satcatPath = PACKAGE_PATH + "/datastore/satcat.csv"
    while not exitCondition.is_set():
        try:
            res = requests.get(SATCAT_POLL_URL)
            with open(satcatPath, 'wb') as f:
                f.write(res.content)
            time.sleep(SATCAT_POLL_INTERVAL_S)
        except KeyboardInterrupt:
            exitCondition.set()

def startTlePoll():
    """
    Periodically (defaults to once every 10 seconds) draws a random SSCID (that
    has not re-entered) from the satcat, then fetches the latest TLE. If it has
    changed, it is stashed and an on-change event is broadcasted to connected
    WebSockets.
    """
    print("Starting TLE poll against %s..." % TLE_POLL_URL)
    exitCondition = threading.Event()
    satcatPath = PACKAGE_PATH + "/datastore/satcat.csv"
    while not exitCondition.is_set():
        print(" => TLE poll tick", flush=True)
        try:
            if not os.path.isfile(satcatPath):
                pass
            sscid = drawSSCID(satcatPath)
            res = requests.get(TLE_POLL_URL % sscid)
            newTle = res.content.splitlines()
            tlePath = PACKAGE_PATH + "/datastore/%u.tle" % sscid
            hasChanged = True
            if os.path.isfile(tlePath):
                with open(tlePath, 'rb') as f:
                    oldTle = f.readlines()
                deltas = difflib.unified_diff(oldTle, newTle)
                hasChanged = 0 < len(deltas)
            if hasChanged:
                with open(tlePath, 'wb') as f:
                    f.write(b"\n".join(newTle))
                broadcastChange(sscid, newTle)
            time.sleep(TLE_POLL_INTERVAL_S)
        except KeyboardInterrupt:
            exitCondition.set()

def startWsgiServer():
    """
    Starts a WebSocket-extended WSGI server from the module's Flask app.
    """
    print("Starting WSGI server at %s:%u..." % (SERVER_HOST, SERVER_PORT))
    pywsgi.WSGIServer((SERVER_HOST, SERVER_PORT), APP, **{
        "handler_class": handler.WebSocketHandler
    }).serve_forever()

def main():
    """
    Kicks off three separate threads: a WSGI server (endpoint definitions for
    WebSockets and others); an intermediate TLE poll; and an intermediate
    satcat poll.
    """
    threads = [
        threading.Thread(group=None, target=startSatcatPoll),
        threading.Thread(group=None, target=startTlePoll),
        threading.Thread(group=None, target=startWsgiServer)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]

if __name__ == "__main__":
    main()
