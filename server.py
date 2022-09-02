"""
"""

import os
import csv
import time
import random
import threading
import flask
import requests
from gevent import pywsgi

PACKAGE_PATH, _ = os.path.split(os.path.abspath(__file__))
_, PACKAGE_NAME = os.path.split(PACKAGE_PATH)
SATCAT_POLL_INTERVAL_S = int(os.getenv("SATCAT_POLL_INTERVAL_S", 3600))
SATCAT_POLL_URL = os.getenv("SATCAT_POLL_URL", "https://celestrak.org/pub/satcat.csv")
TLE_POLL_INTERVAL_S = int(os.getenv("TLE_POLL_INTERVAL_S", 60))
TLE_POLL_URL = os.getenv("TLE_POLL_URL", "https://celestrak.org/NORAD/elements/gp.php?CATNR=%u")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
APP = flask.Flask(PACKAGE_NAME)

def drawSSCID(satCatPath):
    """
    """
    with open(satCatPath, 'r') as f:
        dr = csv.DictReader(f)
        rows = [row for row in dr]
    alive = [row for row in rows if row["DECAY_DATE"] == ""]
    draw = random.choice(alive)
    return int(draw["NORAD_CAT_ID"])

def startSatcatPoll():
    """
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
    """
    print("Starting TLE poll against %s..." % TLE_POLL_URL)
    exitCondition = threading.Event()
    satcatPath = PACKAGE_PATH + "/datastore/satcat.csv"
    while not exitCondition.is_set():
        try:
            if not os.path.isfile(satcatPath):
                pass
            sscid = drawSSCID(satcatPath)
            res = requests.get(TLE_POLL_URL % sscid)
            tlePath = PACKAGE_PATH + "/datastore/%u.tle" % sscid
            with open(tlePath, 'wb') as f:
                f.write(res.content)
            time.sleep(TLE_POLL_INTERVAL_S)
        except KeyboardInterrupt:
            exitCondition.set()

@APP.route("/<path:filename>")
def index(filename):
    """
    """
    return flask.send_from_directory(PACKAGE_PATH + "/datastore", filename, mimetype="text/plain")

def startWsgiServer():
    """
    """
    print("Starting WSGI server at %s:%u..." % (SERVER_HOST, SERVER_PORT))
    pywsgi.WSGIServer((SERVER_HOST, SERVER_PORT), APP).serve_forever()

def main():
    """
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
