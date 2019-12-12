  
**npkh - Namecoin PGP Key Handler**  
===============================  
  
Allows you to make sure you are using the right PGP key by entering a Namecoin ID (id/ namespace) in your favorite keyserver client (PGP software) and getting a secure fingerprint from the Namecoin blockchain.  
  
**How it works**  
Namecoin PGP Key Handler mimics a standard PGP keyserver locally using the OpenPGP HTTP Keyserver Protocol (HKP). It adds functionality to request PGP keys for Namecoin IDs via a long fingerprint saved in the name value. This can be done through any application that can query a keyserver, e.g. Enigmail. By doing so you can make quite sure you are using the right PGP key. Standard (non Namecoin) PGP key requests will be passed through to a standard PGP keyserver.  
  
**Current features**  
* will do exact match lookups on id/  
* will take a long (>40 characters) key fingerprint from the value field '/gpg/fpr' or '/fpr'  
* will download keys from the location specified in the value or from a standard keyserver  
* will proxy normal lookups to a standard keyserver  
* can be run as plugin for Namecoin's NMControl or in standalone mode  
* Known limitation: will not work with NMControl as global DNS provider (which is not a good idea anyway).  
  
**How to run**  
* run Namecoin Client (blockchain must be completely downloaded) or a drop in replacement (SPV client)  
* Python 3 or Python 2.7.x must be installed (NMControl only works with Python 2.7.x)  
  
in standalone mode:  
* download: e.g. `git clone https://github.com/phelix/npkh`  
* install requirements: `pip install --upgrade -r requirements.txt`  
* run local server: `python ./npkh.py --serv`  
* or do a command line query `python ./npkh.py get id/phelix`  
* configuration by editing defaults in pluginKeyHandler.py  
  
as NMControl plugin:  
* put pluginKeyHandler.py into the NMControl subfolder 'plugin'  
* launch NMControl (stop other instances first then launch e.g. from the command line with: `python ./nmcontrol.py --debug=1`)  
* configuration via NMControl conf file plugin-keyServer.conf  
  
then:  
* from PGP enabled eMail program (tested with Thunderbird) --> enigmail --> key management --> keyserver  
* as keyserver enter 127.0.0.1:8083 (default)  
* search for e.g. id/domob id/phelix id/jeremy  
* you can also search for non id/ keys as usual  
  
**Notes**
continued from https://forum.namecoin.org/viewtopic.php?f=9&t=2476  
On Github: https://github.com/phelix/npkh  
License: MIT  
