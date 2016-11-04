"""
Portal Scheduler. Logger class

Package zLOG exists only for backward compatibility.  Any new code
for Zope 2.8 and newer should use the logging module from Python's
standard library directly.  zLOG is only an API shim to map existing
use of zLOG onto the standard logging API.

*** Checked 05/03/2009 ***

"""
import os
import Globals

try:
    from zLOG.MinimalLogger import stupid_log_write, _log_level, log_time, \
         severity_string, format_exception
except ImportError:
    from traceback import format_exception
    from zLOG.EventLogger import log_write, log_time, severity_string

    class stupid_log_write:
        def __init__( self ):
            self.initialize()

import Config

_log_dest = None
_log_level = None

# We have to copy the most of the minimal logger's code in order to use our own
# _log_dest and _log_level globals.

def _set_log_dest(dest):
    global _log_dest
    _log_dest = dest


class SchedulerLog( stupid_log_write ):

    def initialize( self ):
        global _log_level
        eget = os.environ.get

        path = eget('SCHEDULER_LOG_FILE')
        if path is None:
           path = os.path.join(Globals.data_dir, Config.DefaultLogFile)
        if path:
            _set_log_dest(open(path, 'a'))
        else:
            _set_log_dest(sys.stderr)

        severity = eget('SCHEDULER_LOG_SEVERITY') or Config.DefaultLogSeverity
        if severity:
            _log_level = int(severity)
        else:
            _log_level = 0

    def log( self, subsystem, severity, summary, detail, error ):
        global _log_dest
        if _log_dest is None or severity < _log_level:
            return

        if detail:
            buf = ("------\n"
                   "%s %s %s %s\n%s" % ( log_time(), severity_string(severity), subsystem, summary, detail ))
        else:
            buf = ("------\n"
                   "%s %s %s %s" % ( log_time(), severity_string(severity), subsystem, summary ))
        print >> _log_dest, buf

        if error:
            try:
                lines = format_exception(error[0], error[1], error[2], limit=100)
                print >> _log_dest, ''.join(lines)
            except:
                print >> _log_dest, "%s: %s" % error[:2]
        _log_dest.flush()

_scheduler_log = SchedulerLog()
log_write = _scheduler_log.log


def LOG( scheduler, severity, summary, detail='', error=None, reraise=None ):
    if not scheduler:
        scheduler = 'Unknown'

    log_write( scheduler, severity, summary, detail, error )
    if reraise and error:
        raise error[0], error[1], error[2]
