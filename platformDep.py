import os
import platform

def getNamecoinDir():
    if platform.system() == "Darwin":
        return os.path.expanduser("~/Library/Application Support/Namecoin")
    elif platform.system() == "Windows":
        return os.path.join(os.environ['APPDATA'], "Namecoin")
    return os.path.expanduser("~/.namecoin")

def getNmcontrolDir():
    if platform.system() == "Darwin":  # Mac OS X
        return os.path.expanduser("~/Library/Application Support/Nmcontrol")
    elif platform.system() == "Windows":  # MS Windows
        return os.path.join(os.environ['APPDATA'], "Nmcontrol")

    # Linux
    try:
        st = os.stat('/var/lib/nmcontrol')
        haspermission = bool(st.st_mode & stat.S_IRGRP)
    except OSError:
        haspermission = False
    if haspermission:
        return '/var/lib/nmcontrol'
    else:
        return os.path.expanduser("~/.config/nmcontrol")
