"""
Global PortalScheduler settings
$Id: Config.py, v 1.0 2008/02/20 12:00:00 Exp $

*** Checked 05/03/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from mx.DateTime import RelativeDateTime

ProductName             = 'PortalScheduler'

QueueExpirationIterval  = RelativeDateTime( minutes=5 )
MaxThreadsCount         = 3
ConflictTimeout         = 3.0
AutoStartDaemonThreads  = 0
DisableScheduler        = 0

DefaultLogFile          = 'scheduler.log'
DefaultLogSeverity      = -500

ActiveState             = 'active'
RunnableState           = 'runnable'
ZombieState             = 'zombie'
SuspendedState          = 'suspended'

# ================================================================================================================

class States: pass

for name, value in globals().items():
    if name[-5:] == 'State':
        States.__dict__[ name[:-5] ] = value

# ================================================================================================================
