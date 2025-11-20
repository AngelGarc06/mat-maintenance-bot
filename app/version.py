# app/version.py
import os
from datetime import datetime

APP_NAME     = "MAT Bot"
APP_VERSION  = os.environ.get("APP_VERSION", "0.1.0")
GIT_SHA      = os.environ.get("GIT_SHA", "").strip() or "dev"
BUILD_TIME   = os.environ.get("BUILD_TIME") or datetime.utcnow().isoformat()

def as_dict():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "git_sha": GIT_SHA[:7],
        "build_time": BUILD_TIME,
    }

def as_text():
    d = as_dict()
    return f"{d['name']} v{d['version']} (commit {d['git_sha']}, build {d['build_time']})"
