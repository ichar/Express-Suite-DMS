"""
PortalLogger
$Id: PortalLogger.py, v 1.0 2009/02/26 12:00:00 Exp $

*** Checked 26/02/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys
import traceback
from types import TupleType, ListType

from AccessControl.SecurityManagement import get_ident

from TransactionManager import check_portal_settings

from logging import getLogger
logger = getLogger()

# ================================================================================================================
#   System Logger extensions
# ================================================================================================================

def portal_log( context, module='', function='', text='', params='', force=None ):
    """
        Print system trace log message
    """
    if not check_portal_settings( context, name='p_log' ) and not force:
        return
    _log( None, '%s%s' % ( module, function and '.%s' % function or '' ), text, params, force )

def print_traceback( exc_traceback=None ):
    """ Print ExpressSuite customized traceback """
    if exc_traceback is None:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        if not exc_traceback:
            return ''
    trace = traceback.extract_tb( exc_traceback )
    out = 'Traceback (innermost last):\n'
    for filename, lineno, function, message in trace:
        out += "  File %s, line %s, in %s\n" % ( filename, lineno, function )
        out += "    %s\n" % message
    out += "Customized specially for Express Suite DMS"
    return out

def _log( method, function='', text='', params='', force=None, **kw ):
    """
        Print system log message.

        Arguments:

            'method'   -- logger method, can be None, default 'logger.info'

            'function' -- (arg) any text, like 'class.method'

            'text'     -- (arg) trace message

            'params'   -- (arg) params tuple

            'force'    -- (arg) Boolean, forced print message 

            'exc_info' -- (kw) for debug mode only, print traceback.

        Implemented for 'portal_info', 'portal_debug', 'portal_error' functions. Arguments should be 'arg'/'kw'.
    """
    thread_id = get_ident()

    if method is None:
        log = logger.info
    else:
        log = method
    if params:
        if type(params) not in ( TupleType, ListType, ):
            params = [params]
        info = "%s %s %s:\n%s" % ( thread_id, function, text, '\n'.join( [ str(x) for x in params ] ) )
    elif text:
        info = "%s %s %s" % ( thread_id, function, text )
    else:
        info = "%s %s" % ( thread_id, function )

    apply( log, (info,), kw )

def portal_info( *args, **kw ):
    """ Print system info log """
    _log( logger.info, *args, **kw )

def portal_debug( *args, **kw ):
    """ Print system debug log """
    _log( logger.debug, *args, **kw )

def portal_error( *args, **kw ):
    """ Print system error log """
    _log( logger.error, *args, **kw )
