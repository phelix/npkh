# Copyright (C) 2014-2015 by phelix / blockchained.com
# Copyright (C) 2013 by Daniel Kraft <d@domob.eu>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# todo: read NMControl config files

# todo: read datadir path from registry

# todo: timeout authproxy
# todo: proper translation of error codes
# todo: setting an empty value does not work
# separate NMControl and client?

import authproxy
import base64
import socket
import json
import sys
import os
import platform
import time
import traceback

import locale
encoding = locale.getpreferredencoding().lower()

COINAPP = "namecoin"
DEFAULTCLIENTPORT =  8336
DEFAULTNMCONTROLPORT =  9000
HOST = "127.0.0.1"

COOKIEAUTH_FILE = ".cookie"

CONTYPECLIENT = "client"
CONTYPENMCONTROL = "nmcontrol"

DEBUG = 0

class RpcError(Exception):
    """Server returned error."""
    pass

class RpcConnectionError(Exception):
    """Connection failed."""
    pass

# raised by comfort calls "nm_..."
class NameDoesNotExistError(Exception):
    pass

# create Exception classes for client errors from error codes
# with results like this:
# class InvalidAddressError(ClientError):
#    code = -4
##    // General application defined errors
##    RPC_MISC_ERROR                  = -1,  // std::exception thrown in command handling
##    RPC_FORBIDDEN_BY_SAFE_MODE      = -2,  // Server is in safe mode, and command is not allowed in safe mode
##    RPC_TYPE_ERROR                  = -3,  // Unexpected type was passed as parameter
##    RPC_INVALID_ADDRESS_OR_KEY      = -5,  // Invalid address or key
##    RPC_OUT_OF_MEMORY               = -7,  // Ran out of memory during operation
##    RPC_INVALID_PARAMETER           = -8,  // Invalid, missing or duplicate parameter
##    RPC_DATABASE_ERROR              = -20, // Database error
##    RPC_DESERIALIZATION_ERROR       = -22, // Error parsing or validating structure in raw format
##    RPC_TRANSACTION_ERROR           = -25, // General error during transaction submission
##    RPC_TRANSACTION_REJECTED        = -26, // Transaction was rejected by network rules
##    RPC_TRANSACTION_ALREADY_IN_CHAIN= -27, // Transaction already in chain
##    // P2P client errors
##    RPC_CLIENT_NOT_CONNECTED        = -9,  // Bitcoin is not connected
##    RPC_CLIENT_IN_INITIAL_DOWNLOAD  = -10, // Still downloading initial blocks
##    // Wallet errors
##    RPC_WALLET_ERROR                = -4,  // Unspecified problem with wallet (key not found etc.)
##    RPC_WALLET_INSUFFICIENT_FUNDS   = -6,  // Not enough funds in wallet or account
##    RPC_WALLET_INVALID_ACCOUNT_NAME = -11, // Invalid account name
##    RPC_WALLET_KEYPOOL_RAN_OUT      = -12, // Keypool ran out, call keypoolrefill first
##    RPC_WALLET_UNLOCK_NEEDED        = -13, // Enter the wallet passphrase with walletpassphrase first
##    RPC_WALLET_PASSPHRASE_INCORRECT = -14, // The wallet passphrase entered was incorrect
##    RPC_WALLET_WRONG_ENC_STATE      = -15, // Command given in wrong wallet encryption state (encrypting an encrypted wallet etc.)
##    RPC_WALLET_ENCRYPTION_FAILED    = -16, // Failed to encrypt the wallet
##    RPC_WALLET_ALREADY_UNLOCKED     = -17, // Wallet is already unlocked

clientErrorCodes = {
    "MiscError" : -1,  # e.g. "there are pending operations on that name"
    "WalletError" : -4,
    "InvalidAddressOrKeyError" : -5,  # also non wallet tx
    "WalletInsufficientFundsError" : -6,
    "InvalidParameterError" : -8,
    "ClientNotConnectedError" : -9,
    "ClientInInitialDownloadError" : -10,
    "WalletUnlockNeededError" : -13,
    "WalletPassphraseIncorrectError" : -14,
    "WalletAlreadyUnlockedError" : -17,
    }

class ClientError(Exception):
    """Base class for client errors."""
    pass

clientErrorClasses = []
for e in clientErrorCodes:
    c = type(e, (ClientError,), {"code":clientErrorCodes[e]})  # create class
    globals()[c.__name__] = c  # register in module
    clientErrorClasses.append(c)  # allow for easy access


class CoinRpc(object):
    """connectionType: auto, nmcontrol or client"""
    def __init__(self, connectionType="auto", options=None, datadir=None, timeout=5):
        self.bufsize = 4096
        self.host = HOST
        self.authServiceProxy = None

        self.timeout = timeout  # If set to None the global default will be used.

        self.connectionType = connectionType
        self.datadir = datadir
        if datadir:
            self.datadir = datadir + "/"
        self.options = options
        if options == None:
            self.options = self.get_options()

        if DEBUG:
            print "options:", self.options

        if not connectionType in [CONTYPECLIENT, CONTYPENMCONTROL]:
            self._detect_connection()

        if self.connectionType == CONTYPECLIENT and not self.authServiceProxy:
            self.setup_authServiceProxy()

    def setup_authServiceProxy(self):
        s = ("http://" + str(self.options["rpcuser"]) + ":" +
            str(self.options["rpcpassword"]) +"@" + self.host +
            ":" + str(self.options["rpcport"]))
        self.authServiceProxy = authproxy.AuthServiceProxy(s)

    def _detect_connection(self):
        options = self.options

        self.connectionType = CONTYPENMCONTROL
        if options == None:
            self.options = self.get_options()
        errorString = ""
        try:
            self.call("help")
            return
        except:
            errorString = traceback.format_exc()

        self.connectionType = CONTYPECLIENT
        if options == None:
            self.options = self.get_options()
        self.setup_authServiceProxy()
        try:
            self.call("help")
        except:
            errorString += "\n\n" + traceback.format_exc()
            raise RpcConnectionError("Auto detect connection failed: " + errorString)

    def call(self, method="getinfo", params=[]):
        if self.connectionType == CONTYPECLIENT:
            val = self.query_server_asp(method, *params)
            #except Exception as e:
              #  raise RpcError(e)
        elif self.connectionType == CONTYPENMCONTROL:
            data = {"method": method, "params": params}
            resp = self.query_server(json.dumps(data))
            resp = resp.decode(encoding)
            val = json.loads(resp)
        else:
            assert False

        if val["error"]:
            if self.connectionType == CONTYPECLIENT:
                for e in clientErrorClasses:
                    if e.code == val["error"]["code"]:
                        raise e(val["error"])
            raise RpcError(val)  # attn: different format for client and nmcontrol

        return val["result"]

    def query_server_asp(self, method, *params):
        val = {"error" : None, "code":None}
        try:
            try:
                val['result'] = self.authServiceProxy.__getattr__(method)(*params)
            except socket.error as e:
                if e.errno == 10053:  # closed by host
                    # workaround for closed connection - why? timeout?
                    if DEBUG:
                        print "connection closed by host, setting up new one"
                    self.setup_authServiceProxy()
                    val['result'] = self.authServiceProxy.__getattr__(method)(*params)
                else:
                    raise
        except authproxy.JSONRPCException as e:
            val = {"error" : e.error}
            try:
                val["code"] = e.error["code"]
            except KeyError:
                val["code"] = "NA"
        return val

    def query_server(self, data):
        """Helper routine sending data to the RPC server and returning the result."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if self.timeout:
                s.settimeout(self.timeout)
            s.connect((self.host, int(self.options["rpcport"])))
            s.sendall(data)
            result = ""
            while True:
                tmp = s.recv(self.bufsize)
                if not tmp:
                  break
                result += tmp
            s.close()
            return result
        except socket.error as exc:
            raise RpcConnectionError("Socket error in RPC connection to " +
                                     "%s: %s" % (str(self.connectionType), str(exc)))

    # ~ nmcontrol platformDep.py
    def get_conf_folder(self, coin=COINAPP):
        coin = coin.lower()
        if platform.system() == "Darwin":
            return os.path.expanduser("~/Library/Application Support/" + coin.capitalize())
        elif platform.system() == "Windows":
            return os.path.join(os.environ['APPDATA'], coin.capitalize())
        return os.path.expanduser("~/." + coin)

    def get_options(self):
        if self.connectionType == CONTYPECLIENT:
            options = {}
            try:
                options = self.get_options_client()
                if DEBUG:
                    print "client options from conf file:", optoins
            except:
                pass
            if not 'rpcuser' in options or not 'rpcpassword' in options:
                # fall back to cookie authentication
                options = self.get_cookie_auth(options)
                if DEBUG:
                    print "client options with cookie auth:", options
            return options
        if self.connectionType == CONTYPENMCONTROL:
            return {"rpcport":DEFAULTNMCONTROLPORT}
        return None

    def get_cookie_auth(self, options):
        if DEBUG:
            print "cookie auth"
        try:
            filename = self.datadir + "/" + COOKIEAUTH_FILE
            with open(filename) as f:
                    line = f.readline()
                    options['rpcuser'], options['rpcpassword'] = line.split (':')
        except IOError as e:
            if e.errno == 2:
                raise IOError(e.errno, "namerpc: Could not open cookie file: " + str(filename))
        return options

    def get_options_client(self):
        """Read options (rpcuser/rpcpassword/rpcport) from .conf file."""
        options = {}
        options["rpcport"] = DEFAULTCLIENTPORT
        if not self.datadir:
            self.datadir = self.get_conf_folder()
        try:
            filename = self.datadir + os.sep + COINAPP + ".conf"
            with open(filename) as f:
                while True:
                    line = f.readline()
                    if line == "":
                        break
                    parts = line.split ("=")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        if key.startswith("#"):
                            continue
                        val = parts[1].strip()
                        options[key] = val
        except IOError as e:
            if e.errno == 2:
                raise IOError(e.errno, "namerpc: Could not open .conf file: " + str(filename))
        return options


    # comfort functions

# better use getinfo
##    def is_locked(self):
##        try:
##            self.call("sendtoaddress", ["", 0.00000001])  # Certainly there is a more elegant way to check for a locked wallet?
##        except WalletUnlockNeededError:
##            return True
##        except (WalletError, InvalidAddressOrKeyError, MiscError):
##            return False

    def chainage(self):
        c = self.call("getblockcount")
        T = 0
        for i in [0, 1, 2]:
            h = self.call("getblockhash", [c - i])
            t = self.call("getblock", [h])["time"]
            T += t + i * 60 * 9  # conservative
        t = T / 3
        return int(round(time.time() - t))

    def blockchain_is_uptodate(self, period=60 * 10 * 10):
        if self.chainage() <= period:
            return True
        else:
            return False

    def nm_show(self, name):
        if self.connectionType == CONTYPENMCONTROL:
            data = self.call("data", ["getData", name])["reply"]
            if data == False:
                raise NameDoesNotExistError()
        else:
            try:
                data = self.call("name_show", [name])
            except WalletError:
                raise NameDoesNotExistError()
        return data

if __name__ == "__main__":
    rpc = CoinRpc(connectionType=CONTYPECLIENT)
    print rpc.call("getblockhash", [33])
    print rpc.call("getinfo")
    #print rpc.nm_show("d/nx")

    # test timeout
    time.sleep(66)
    print rpc.call("getinfo")

    if len(sys.argv) == 1:
        print "========auto detect"
        rpc = CoinRpc()  # default: connectionType="auto"
        print "detected:", rpc.connectionType

        print "\n\n========NMControl"
        try:
            rpc = CoinRpc(connectionType=CONTYPENMCONTROL)
            print rpc.call("help")["reply"]
            print rpc.nm_show("d/nx")
        except:
            traceback.print_exc()

        print "\n\n========Namecoind"
        rpc = CoinRpc(connectionType=CONTYPECLIENT)
        print "options:", rpc.options
        print rpc.call("getinfo")
        print rpc.nm_show("d/nx")

        print '\n\n========Command line usage examples'
        print 'namerpc.py getinfo'
        print 'namerpc.py name_show d/nx'

    else:
        import pprint
        rpc = CoinRpc()
        if sys.argv[1] == "nm_show":
            pprint.pprint(rpc.nm_show(sys.argv[2]))
        else:
            pprint.pprint(rpc.call(sys.argv[1], sys.argv[2:]))
