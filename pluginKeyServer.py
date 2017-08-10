# -*- coding: utf-8 -*-

DEFAULTHOST = "127.0.0.1"  # 0.0.0.0 allows public access
DEFAULTPORT = "8083"
DEFAULTKEYSERVER = "sks-keyservers.net"

# workaround to make bottle stoppable - this can be cleaned up with bottle 0.13
import wsgiref.simple_server
original_make_server = wsgiref.simple_server.make_server
def my_make_server(*args, **kwargs):
    server = original_make_server(*args, **kwargs)
    args[2].server = server  # app
    return server
wsgiref.simple_server.make_server = my_make_server
# now stop via app.server.shutdown()

def remove_value(dic, value):
    """remove all items with value if any (in place)"""
    for k, v in dic.items():
        if v == value:
           del dic[k]

import re
ALLOWEDRE = "^id/[a-z0-9]+([-]?[a-z0-9])*$"
reg = re.compile(ALLOWEDRE)

standalone = False
if __name__ == "__main__":
    standalone = True
    import sys
    sys.path.append("../lib")  # for standalone debugging
    sys.path.append("../../nameGUI/lib")  # for standalone debugging

    import namerpc
    tmpRpc = namerpc.CoinRpc(connectionType="auto")  # cache looked up rpc options
    rpcConnectionType = tmpRpc.connectionType
    rpcOptions = tmpRpc.options
    del tmpRpc

import os
import json
import urllib2
import copy
import bottle

import common
if standalone:
    common.app['debug'] = True
import plugin

log = common.get_logger(__name__)

if standalone:
    log.debug("rpcConnectionType:", rpcConnectionType)
    log.debug("rpcOptions:", rpcOptions)

class pluginKeyServer(plugin.PluginThread):
    name = 'keyServer'
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
        log.debug("Plugin %s parent start" %(self.name))
        self.keyServer = KeyServer()
        self.running = 1
        self.keyServer.start()

    def pStop(self, arg = []):
        log.debug("Plugin %s parent stop" %(self.name))
        if not self.running:
            return True
        self.keyServer.stop()
        self.running = False
        self.server = None
        return True

##import pgpdump
##
##def get_fingerprint(asciiArmored):
##    a = pgpdump.AsciiData(asciiArmored)
##    p = a.packets()
##    n = p.next()
##    return n.fingerprint

class IdRequest(object):
    def __init__(self, name):
        if not reg.match(name):
            bottle.abort(400, "Wrong id/ format.")
        self.name = name

    def get_value(self, name):
        try:
            value = common.app['plugins']['data'].getValueProcessed(name)
        except Exception as e:  # todo: proper error handling in NMControl
            bottle.abort(502, "Backend error (NMControl internal): " + repr(e))
        if value == False:
            bottle.abort(404, "Name not found.")
        log.debug("get_value value:", type(value), value)
        return value

    def get_fpr(self):
        self.value = self.get_value(self.name)

        # fetch fpr
        try:
            fpr = self.value["gpg"]["fpr"]
        except KeyError:
            try:
                fpr = self.value["fpr"]  # untidy?
            except KeyError:
                bottle.abort(415, "No fingerprint found in " + unicode(self.name))
        fpr = fpr.lower()
        # check fpr
        try:
            int(fpr, base=16)
        except ValueError:
            bottle.abort(415, "Bad fingerprint.")
        if len(fpr) < 40:  # 40: sha1
            bottle.abort(415, "Insecure fingerprint.")
        self.fpr = fpr
        return fpr

    def get_index(self):
        #"pub:<keyid>:<algo>:<keylen>:<creationdate>:<expirationdate>:<flags>"

        s = "info:1:1\n"
        s += "pub:" + self.fpr + "\n"

        n = [self.name]
        for f in ["name", "email", "country", "locality"]:
            if f in self.value:
                if type(self.value[f]) == list:
                    v = self.value[f][0]
                elif type(self.value[f]) == dict:
                    v = self.value[f]["default"]
                else:
                    v = self.value[f]
                n.append(urllib2.quote(v))
        s += "uid:" + " - ".join(n)

        log.debug("get_index s:", s)
        return s

    def url_read(self, url):
# todo: make this work with NMControl as global system DNS source (also see proxy_to_standard_pks below)
##        try:
##            # getaddrinfo is not thread safe
##            urlParts = urllib2.urlparse.urlparse(url)
##            ip = common.app['services']['dns'].lookup({'domain':urlParts.netloc, 'qtype':1})[0]["data"]
##            urlIp = urlParts._replace(netloc=ip).geturl()
##            headers = { 'Host' : urlParts.netloc }
##            req = urllib2.Request(urlIp, headers=headers) #origin_req_host=urlParts.netloc)
##            log.debug("--------------req:", req)
##
##            k = urllib2.urlopen(req).read()
##            #k = urllib2.urlopen(url).read()  # dangerous?
##        except KeyError:  # standalone without NMControl
        k = urllib2.urlopen(url).read()  # dangerous?
        return k

    def get_key(self, standardKeyServer):
        try:
            url = self.value["gpg"]["uri"]
            log.debug("get_key: trying custom key url:", url)
            k = self.url_read(url)
        except: #  (KeyError, urllib2.URLError, urllib2.HTTPError):
            url = ("https://" + standardKeyServer +
                   "/pks/lookup?op=get&options=mr&search=0x" + self.fpr)
            log.debug("get_key: trying keyserver url:", url)
            k = self.url_read(url)
        log.debug("get_key: ok, len: " + str(len(k)))
        #if get_fingerprint(k) != search:  # should be checked by gpg
         #   bottle.abort(415, "Fingerprint mismatch.")
        return k

class StandaloneIdRequest(IdRequest):
    def get_value(self, name):
        rpc = namerpc.CoinRpc(connectionType=rpcConnectionType,
                              options=rpcOptions)
        try:
            data = rpc.nm_show(name)
        except namerpc.NameDoesNotExistError:
            bottle.abort(404, "Name not found.")
        except namerpc.RpcError:
            bottle.abort(502, "Backend error (rpc).")

        try:
            data = json.loads(data)
        except TypeError:
            pass
        value = data["value"]
        try:
            value = json.loads(value)
        except TypeError:
            pass
        log.debug("get_value value:", type(value), value)
        return value

class RequestHandler(object):
    def __init__(self, standardKeyServer=DEFAULTKEYSERVER, standalone=False):
        self.idFprs = {}  # all lowercase so we don't have to handle 0X instead of 0x
        self.standardKeyServer = standardKeyServer
        self.standalone = standalone
        log.debug("New RequestHandler")

    def proxy_to_standard_pks(self, request):
        # currently this will break with NMControl as global system DNS because of
        # getaddrinfo not being thread safe (see get_key above)
        log.debug("proxying to " + self.standardKeyServer)
        url = request.urlparts._replace(  # _replace is a public function despite the underscore
                        netloc=self.standardKeyServer, scheme="https").geturl()
        log.debug("modified request:", url)
        return urllib2.urlopen(url).read()

    def lookup_req(self, request):
        search = request.query.search
        op = request.query.op
        return self.lookup(search, op, request=request)

    def lookup(self, search, op, request=None):
        name = None
        if search.startswith("id/"):
            name = search

        searchFpr = None
        if search.lower() in self.idFprs:
            searchFpr = search.lower()

        log.debug("lookup: search:", search, " name:", name, " searchFpr:", searchFpr,
                  " request:", request != None, " op:", op, len(self.idFprs), self.idFprs)
        if not name and not searchFpr:
            if request:
                return self.proxy_to_standard_pks(request)
            else:
                bottle.abort(403, "No request and search not recognized: " + unicode(search))

        # allow index of keys in idFprs
        if searchFpr:
            name = self.idFprs[searchFpr]

        log.debug("lookup: id/:", name, "searchFpr:", searchFpr)

        if not standalone:
            idRequest = IdRequest(name)
        else:
            idRequest = StandaloneIdRequest(name)

        fpr = idRequest.get_fpr()

        # if searching by fingerprint make sure to adhere
        if searchFpr and searchFpr != "0x" + fpr:
            bottle.abort(503, "Fingerprint mismatch. Out of date?")

        # keep cache up to date
        remove_value(self.idFprs, name)  # maybe a key was revoked (in place operation)
        cacheFpr = "0x" + fpr.lower()
        self.idFprs[cacheFpr] = name
        log.debug("lookup: updated cache:", name, cacheFpr, len(self.idFprs))

        if op == "index":
            log.debug("index:", name)
            return idRequest.get_index()
        elif op == "get":
            log.debug("get:", name)
            k = idRequest.get_key(self.standardKeyServer)
            return k
        else:
            abort(501, "Not implemented.")

class KeyServer(object):
    def __init__(self, host=DEFAULTHOST, port=DEFAULTPORT,
                 standardKeyServer=DEFAULTKEYSERVER,
                 standalone=False):
        self.host = host
        self.port = port
        self.standardKeyServer = standardKeyServer
        self.standalone = standalone
        self.app = bottle.Bottle()
        self.app.route('/pks/lookup', ['GET', 'POST'], self.serve)
        self.app.route('/pks/add', ['GET', 'POST'], self.httpError501)  # as per the hkp spec
        self.rh = RequestHandler(self.standardKeyServer, standalone=self.standalone)

    def start(self):
        bottle.run(self.app, host=DEFAULTHOST, port=DEFAULTPORT)

    def stop(self):
        self.app.server.shutdown()  # todo: simplify with bottle v0.13

    def serve(self):
        log.debug("request url:", bottle.request.url)

        return self.rh.lookup_req(bottle.request)

    def httpError501(self):
        bottle.abort(501, "Not implemented.")


import socket


if __name__ == "__main__":
    print "nmcKeyServer: standalone"
    if 1:
        ks = KeyServer()
        ks.start()
    else:
        # testing
        if 0:
            rh = RequestHandler(standalone=True)
            print rh.lookup('id/phelix', 'index') + "\n"
            print rh.lookup('0xFC819E25D6AC1119F748479DCBF940B772132E18', 'index') + "\n"
            print rh.lookup('id/phelix', 'get')[:100] + "...\n"  # public keyserver
            print rh.lookup('id/domob', 'get')[:100] + "...\n"  # custom server
        else:
            print urllib2.urlopen("http://127.0.0.1:8083/pks/lookup?search=antonopoulos&op=index&options=mr").read()[0:100] + "...\n"
            print urllib2.urlopen("http://127.0.0.1:8083/pks/lookup?search=id/phelix&op=index").read() + "\n"
            print urllib2.urlopen("http://127.0.0.1:8083/pks/lookup?search=0xFC819E25D6AC1119F748479DCBF940B772132E18&op=index").read() + "\n"
            print urllib2.urlopen("http://127.0.0.1:8083/pks/lookup?search=id/phelix&op=get").read()[0:100] + "..." + "\n"
            print urllib2.urlopen("http://127.0.0.1:8083/pks/lookup?search=id/domob&op=get").read()[0:100] + "..." + "\n"
