#!/usr/bin/env python
from __future__ import print_function

import sys

import common
common.app["debug"] = False
if "--debug" in sys.argv:
    common.app["debug"] = True
    sys.argv.remove("--debug")

import pluginKeyHandler
# set IdRequest class
pluginKeyHandler.IdRequest = pluginKeyHandler.StandaloneIdRequest

urlopen = pluginKeyHandler.urlopen

# nicer exceptions for command line
def raise_exception(code, message):
    raise Exception(str(code) + ": " + str(message))
pluginKeyHandler.bottle.abort = raise_exception

def help():
    print("npkh - Namecoin PGP Key Handler v0.2")
    print()
    print("npkh index id/phelix")
    print("npkh get id/phelix")
    print("npkh get 0xFC819E25D6AC1119F748479DCBF940B772132E18")
    print()
    print("--serve (needs Namecoin client running)")
    print("--rpcinfo")
    print("--debug")
    print("--test_direct")
    print("--test_query (needs server running)")

# inspect command line
for op in ["get", "index"]:
    try:
        pos = sys.argv.index(op)
        arg = sys.argv[pos + 1]
        break
    except (ValueError, IndexError):
        op = None
        pass

if "--help" in sys.argv:
    help()
elif "--serve" in sys.argv:
    ks = pluginKeyHandler.KeyServer()
    ks.start()
elif "--rpcinfo" in sys.argv:
    print(pluginKeyHandler.rpcConnectionType)
    print(pluginKeyHandler.rpcOptions)
elif "--test_direct" in sys.argv:
        print("testing...")
        def parse_fpr(s):
            s = s.split("\n")[1]
            s = s.replace("pub:", "0x")
            s = s.split(":")[0]
            return s
        rh = pluginKeyHandler.RequestHandler()

        s = str(rh.lookup("id/phelix", "index"))
        print(s + "\n")
        fpr = parse_fpr(s)
        print("fpr:", fpr)
        print(str(rh.lookup(fpr, "index")) + "\n")  # will detect id from cache and check whether it's still up to date
        print(str(rh.lookup(fpr, "get"))[:100] + "\n")

        s = str(rh.lookup("id/domob", "index"))
        print(s + "\n")
        fpr = parse_fpr(s)
        print("fpr:", fpr)
        print(str(rh.lookup(fpr, "get"))[:100] + "...\n")  # domob is offering a custom server which we will use to get the key
elif "--test_query" in sys.argv:
        def url_read(url):
            with urlopen(url) as response:
                return response.read().decode('utf-8')
        print(url_read("http://127.0.0.1:8083/pks/lookup?search=antonopoulos&op=index&options=mr")[0:100] + "...\n")
        print(url_read("http://127.0.0.1:8083/pks/lookup?search=id/phelix&op=index") + "\n")
        print(url_read("http://127.0.0.1:8083/pks/lookup?search=id/domob&op=index") + "\n")
        print(url_read("http://127.0.0.1:8083/pks/lookup?search=0xFC819E25D6AC1119F748479DCBF940B772132E18&op=index") + "\n")
        print(url_read("http://127.0.0.1:8083/pks/lookup?search=0xFC819E25D6AC1119F748479DCBF940B772132E18&op=get")[0:100] + "..." + "\n")
        print(url_read("http://127.0.0.1:8083/pks/lookup?search=0x1142850e6dff65ba63d688a8b2492ac4a7330737&op=get")[0:100] + "..." + "\n")
elif op:
    rh = pluginKeyHandler.RequestHandler()
    print(str(rh.lookup(arg, op)))
else:
    raise Exception("error / nothing to do (--help for help)")
