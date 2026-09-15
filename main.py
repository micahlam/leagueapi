import datetime as dt
import json
import os
import ssl
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from urllib import error, parse, request


PLATFORM_REGIONS = [
    "na1",
    "br1",
    "eun1",
    "euw1",
    "jp1",
    "kr",
    "la1",
    "la2",
    "oc1",
    "tr1",
    "ru",
    "ph2",
    "sg2",
    "th2",
    "tw2",
    "vn2",
]

