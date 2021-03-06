# -*- coding: utf-8 -*-

DEFAULTHOST = "127.0.0.1"  # 0.0.0.0 allows public access
DEFAULTPORT = "8083"
DEFAULTKEYSERVER = "sks-keyservers.net"  # only TLS enabled servers!

CACHETIMETOLIVEMINUTES = 5
MAXCACHESIZE = 10

"""
The main OpenPGP HTTP Keyserver Protocol functions are 'index' to search for a list
of keys and 'get' to retrieve a pgp key corresponding to a fingerprint. PGP keys are
usually looked up by first doing an 'index' operation and then a 'get' operation
requesting the PGP key by fingerprint. Because of this we need to cache fingerprints
for Namecoin ID lookups so that we know whether a fingerprint belongs to a
Namecoin ID. Unlike normal requests PGP keys for Namecoin IDs might be
downloaded from a custom website as specified in the name value. Also it will be
verified a cached fingerprint is still up to date.
Note: The integrity of the returned data will be validated externally in GPG (e.g.
verifying that a key matches a long fingerprint).

"""

# workaround to make bottle stoppable - this can be cleaned up with bottle 0.13
import wsgiref.simple_server
original_make_server = wsgiref.simple_server.make_server
def my_make_server(*args, **kwargs):
    server = original_make_server(*args, **kwargs)
    args[2].server = server  # app
    return server
wsgiref.simple_server.make_server = my_make_server
# now stop via app.server.shutdown()

# Python3 compatibility
try:
    unicode("")
except NameError:
    unicode = str

def remove_value(dic, value):
    """remove all items with value if any (in place)"""
    for k, v in list(dic.items()):
        if v == value:
           del dic[k]

import re
ALLOWEDRE = "^id/[a-z0-9]+([-]?[a-z0-9])*$"
reg = re.compile(ALLOWEDRE)

import json

import contextlib

try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+
try:
    from urllib2 import urlopen as urlopen_orig # Python 2.X
except ImportError:
    from urllib.request import urlopen as urlopen_orig  # Python 3+

def urlopen(url):  # ensure "with"-context manager also in Python 2
    return contextlib.closing(urlopen_orig(url))

import bottle

from expiringdict import ExpiringDict


import common

if __name__ == "__main__":
    common.app['debug'] = True

import plugin

log = common.get_logger(__name__)

# Code to work as NMControl plugin
class pluginKeyHandler(plugin.PluginThread):
    name = 'keyHandler'
    options = {
        'start' : ['Launch at startup', 1],
        'host' : ['Listen on ip', DEFAULTHOST, '<ip>'],
        'port' : ['Listen on port', DEFAULTPORT, '<port>'],
        'keyserver' : ['Proxy keyserver', DEFAULTKEYSERVER, '<keyserver>'],
    }
    server = None

    def pStart(self):
        if self.server:
            return
        log.debug("Plugin %s parent start" % (self.name))
        self.keyServer = KeyServer()
        self.running = 1
        self.keyServer.start()

    def pStop(self, arg = []):
        log.debug("Plugin %s parent stop" % (self.name))
        if not self.running:
            return True
        self.keyServer.stop()
        self.running = False
        self.server = None
        return True

import pgpdump
def calc_fingerprint(asciiArmored):
    a = pgpdump.AsciiData(asciiArmored)
    p = a.packets()
    try:  # python 2 compatibility
        n = p.next()
    except AttributeError:
        n = next(p)
    fpr = "0x" + n.fingerprint.lower().decode("utf-8")
    log.debug("calc_fingerprint:", fpr)
    return fpr

def validate_fingerprint(fpr, s):
    calculatedFpr = calc_fingerprint(s)
    if not "0x" in fpr:
        fpr = "0x" + fpr
    try:
        assert fpr.lower() == calculatedFpr
    except AssertionError:
        log.debug("validate_fingerprint: Query does not match calculated fingerprint:", fpr.lower(), calculatedFpr)
        raise
    else:
        log.debug("validate_fingerprint: proxy_to_standard_pks: match", calculatedFpr)

class BaseIdRequest(object):
    def __init__(self, name, standardKeyServer):
        if not reg.match(name):
            bottle.abort(400, "Wrong id/ format.")
        self.name = name
        self.standardKeyServer = standardKeyServer
        self.__init2__()

        self.value = self.get_value(self.name)
        self.fpr = self._extract_fpr()

    def __init2__(self):
        pass

    def get_fpr(self):
        return self.fpr

    def _extract_fpr(self):
        # extract fpr
        try:
            fpr = self.value["gpg"]["fpr"]
        except KeyError:
            try:
                fpr = self.value["fpr"]  # untidy?
            except KeyError:
                bottle.abort(415, "No fingerprint found in " + str(self.name))
        fpr = fpr.lower()

        # check fpr
        try:
            int(fpr, base=16)
        except ValueError:
            bottle.abort(415, "Bad fingerprint.")
        if len(fpr) < 40:  # 40: sha1
            bottle.abort(415, "Insecure fingerprint.")
        return fpr

    def get_value(self, name):  # is overwritten for standalone mode in class StandaloneIdRequest
        try:
            value = common.app['plugins']['data'].getValueProcessed(name)
        except Exception as e:  # todo: proper error handling in NMControl
            bottle.abort(502, "Backend error (NMControl internal): " + repr(e))
        if value == False:
            bottle.abort(404, "Name not found or expired.")  # NMControl does not deliever expired names
        log.debug("get_value value:", type(value), value)
        return value

    def get_time(self):  # NMControl does not support name creation date information nor rpc queries
        nameTime = 468374400  # 1984-11-04
        return nameTime

    def get_index(self):
        #"pub:<keyid>:<algo>:<keylen>:<creationdate>:<expirationdate>:<flags>"

        age = self.get_time()

        s = "info:1:1\n"
        s += "pub:" + self.fpr + ":::" + str(age) + "::\n"

        n = [self.name]
        for f in ["name", "email", "country", "locality"]:
            if f in self.value:
                if type(self.value[f]) == list:
                    v = self.value[f][0]
                elif type(self.value[f]) == dict:
                    v = self.value[f]["default"]
                else:
                    v = self.value[f]
                n.append(quote(v))
        s += "uid:" + " - ".join(n) + "\n"

        log.debug("get_index s:", s)
        return s

    def get_key(self):
        try:
            url = self.value["gpg"]["uri"]
            log.debug("get_key: trying custom key url:", url)
            with urlopen(url) as response:
                k = response.read()
        except:
            url = ("https://" + self.standardKeyServer +
                   "/pks/lookup?op=get&options=mr&search=0x" + self.fpr)
            log.debug("get_key: trying keyserver url:", url)
            with urlopen(url) as response:
                k = response.read()
        validate_fingerprint(self.fpr, k)
        log.debug("get_key: ok, len: " + str(len(k)))
        return k

class StandaloneIdRequest(BaseIdRequest):
    def __init2__(self):
        log.debug("StandaloneIdRequest: init2")
        self.rpcConnectionType = None
        global namerpc
        import namerpc

    def get_rpc(self):
        if not self.rpcConnectionType:
            log.debug("get_rpc: init rpc")
            tmpRpc = namerpc.CoinRpc(connectionType="auto")
            self.rpcConnectionType = tmpRpc.connectionType
            self.rpcOptions = tmpRpc.options
        return namerpc.CoinRpc(connectionType=self.rpcConnectionType,
                              options=self.rpcOptions)

    def rpc(self, method, args=[]):
        rpc = self.get_rpc()
        log.debug("StandaloneIdRequest:rpc: ", repr(method), repr(args))
        return rpc.call(method, args)

    def get_data(self):
        try:
            data = self.rpc("name_show", [self.name])
        except namerpc.NameDoesNotExistError:
            bottle.abort(404, "Name not found: " + str(self.name))
        except namerpc.RpcError:
            bottle.abort(502, "Backend error (rpc).")

        try:
            data = json.loads(data)
        except TypeError:
            pass
        if data["expired"] != False:
            bottle.abort(498, "id/ name is expired: " + str(self.name))

        return data

    def get_value(self, name):
        data = self.get_data()
        value = data["value"]

        try:
            value = json.loads(value)
        except TypeError:
            pass
        except ValueError:  # generic error from json decode
            bottle.abort(415, "Error json decoding name value for " + str(name))

        log.debug("get_value value:", type(value), value)
        return value

    def get_time(self):
        try:
            data = self.get_data()
            height = data["height"]
            blockHash = self.rpc("getblockhash", [height])
            nameTime = self.rpc("getblockheader", [blockHash])["mediantime"]
            log.debug("get_time:nameTime", nameTime)
        except Exception as e:
            log.debug("get_time: Exception: " + repr(e))
            nameTime = 468374400  # 1984-11-04
        return nameTime

class IdRequest(BaseIdRequest):
    pass

class RequestHandler(object):
    def __init__(self, standardKeyServer=DEFAULTKEYSERVER):
        # cache for connecting fingerprints to names - all lowercase so we don't have to handle 0X instead of 0x
        self.idFprs = ExpiringDict(max_len=MAXCACHESIZE, max_age_seconds=60*CACHETIMETOLIVEMINUTES)
        self.standardKeyServer = standardKeyServer
        log.debug("New RequestHandler")

    def build_url(self, search, op):
        url = "https://" + self.standardKeyServer + "/pks/lookup?search=" + search + "&op=" + op
        url += "&options=mr"  # text
        log.debug("build_url:", url)
        return url

    def proxy_to_standard_pks(self, request, search, op):
        """Pass request through to default keyserver."""
        # currently this will break with NMControl as global system DNS because of
        # getaddrinfo not being thread safe
        log.debug("proxying to " + self.standardKeyServer)
        if request:
            url = request.urlparts._replace(  # _replace is a public function despite the underscore
                        netloc=self.standardKeyServer, scheme="https").geturl()
            log.debug("modified request:", url)
        else:
            url = self.build_url(search, op)
        with urlopen(url) as response:
            s = response.read()
        if op.lower() == "get":
            validate_fingerprint(search, s)
        log.debug("proxying done. bytes:", len(s))
        return s

    def get_cached_name(self, fpr):
        name = self.idFprs[fpr]
        return name

    def update_cache(self, name, fpr):
        remove_value(self.idFprs, name)  # maybe a key was revoked (in place operation)
        cacheFpr = "0x" + fpr.lower()
        self.idFprs[cacheFpr] = name
        log.debug("lookup: updated cache:", name, cacheFpr, len(self.idFprs))

    def lookup_from_name(self, name, op):
        log.debug("lookup_from_name: ", name, " op:", op)
        idRequest = IdRequest(name, self.standardKeyServer)
        fpr = idRequest.get_fpr()
        self.update_cache(name, fpr)
        if op == "get":
            return idRequest.get_key()
        return idRequest.get_index()

    def lookup_op_from_idFpr(self, idFpr, op):
        log.debug("lookup_idFpr", idFpr, op)
        name = self.get_cached_name(idFpr)

        # is the requested fingerprint still the correct one for the name in the cache or is the cache wrong by now?
        idRequest = IdRequest(name, self.standardKeyServer)
        currentFpr = idRequest.get_fpr()
        if idFpr != "0x" + currentFpr:
            bottle.abort(503, "Fingerprint mismatch. Out of date?")

        if op == "index":
            return idRequest.get_index()
        elif op == "get":
            return idRequest.get_key()  # will try custom server, then standardKeyServer

    def lookup_req(self, request):
        bottle.response.content_type = 'text/plain; charset=utf-8'
        search = request.query.search
        op = request.query.op
        if op not in ["get", "index"]:
            bottle.abort(501, "Operation not implemented: " + str(op))
        return self.lookup(search, op, request=request)

    def lookup(self, search, op, request=None):
        log.debug("lookup: search:", search, " request:", request != None, " op:", op, len(self.idFprs))

        # looking up a Namecoin id/ ?
        if search.startswith("id/"):
            name = search
            return self.lookup_from_name(name, op)

        # looking up a cached fingerprint?
        if search.lower() in self.idFprs:
            idFpr = search.lower()
            return self.lookup_op_from_idFpr(idFpr, op)

        # if neither looking for a Namecoin id/ nor for a fingerprint - hand over to standard keyserver
        return self.proxy_to_standard_pks(request, search, op)

class KeyServer(object):
    def __init__(self, host=DEFAULTHOST, port=DEFAULTPORT,
                 standardKeyServer=DEFAULTKEYSERVER):
        self.host = host
        self.port = port
        self.standardKeyServer = standardKeyServer
        self.app = bottle.Bottle()
        self.app.route('/pks/lookup', ['GET', 'POST'], self.serve)
        self.app.route('/pks/add', ['GET', 'POST'], self.httpError501)  # as per the hkp spec
        self.rh = RequestHandler(self.standardKeyServer)

    def start(self):
        bottle.run(self.app, host=DEFAULTHOST, port=DEFAULTPORT)

    def stop(self):
        self.app.server.shutdown()  # todo: simplify with bottle v0.13

    def serve(self):
        log.debug(".............. request url:", bottle.request.url)

        return self.rh.lookup_req(bottle.request)

    def httpError501(self):
        bottle.abort(501, "Not implemented.")
