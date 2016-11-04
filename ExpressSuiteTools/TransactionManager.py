"""
TransactionManager
$Id: TransactionManager.py, v 1.0 2009/02/26 12:00:00 Exp $

*** Checked 24/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import threading
import transaction

from Acquisition import aq_get
from AccessControl.SecurityManagement import get_ident
from Products.CMFCore.utils import getToolByName

from ZODB.POSException import ConflictError

import Config

from logging import getLogger
logger = getLogger( 'TransactionManager' )

# ================================================================================================================
#   Thread's ZODB COMMIT HOOKS
# ================================================================================================================

def _unrestrictedGetObjectByUid( context, uid ):
    """
        Returns an object inside the portal by given uid
    """
    catalog = getToolByName( context, 'portal_catalog', None )
    if catalog is None:
        return None
    return catalog.unrestrictedGetObjectByUid( uid )

def getZCatalogInstances( context, no_registries=None ):
    """
        Returns list of portal ZCatalog instances
    """
    res = []
    # portal_catalog
    catalog = getToolByName( context, 'portal_catalog', None )
    if catalog is None:
        return []
    res.append( catalog )
    # portal_followup
    followup = getToolByName( context, 'portal_followup', None )
    if followup is not None:
        res.append( followup )
    # portal_links
    links = getToolByName( context, 'portal_links', None )
    if links is not None:
        res.append( links )
    # registries
    if not no_registries:
        for x in catalog.unrestrictedSearch( meta_type='Registry' ):
            try:
                ob = x.getObject()
            except:
                ob = None
            if ob is not None:
                res.append( ob )
    return res

def IsThreadActivated( catalog ):
    try:
        if catalog is None or getattr(catalog, '_catalog', None) is None or not hasattr(catalog._catalog, 'isThreadActivated'):
            if Config.IsPortalDebug:
                logger.error( 'Member *isThreadActivated* is not defined for catalog: %s. Please delete it!' % `catalog` )
            return None
        return catalog._catalog.isThreadActivated()
    finally:
        pass

def InitActivatedThread( context ):
    """
        Initilizes catalog actions log
    """
    if context is None:
        return 0
    REQUEST = aq_get( context, 'REQUEST', None )
    if REQUEST is None:
        return 0

    p_log = check_portal_settings( context, name='p_log' )

    IsDone = 0
    for catalog in getZCatalogInstances( context ):
        if catalog._catalog.initThread( REQUEST, p_log ):
            IsDone = 1

    return IsDone

def BeginThread( context, klass=None, force=None ):
    """
        Begins thread's transaction
    """
    thread_id = get_ident()

    if not force:
        return 1
    if not check_portal_settings( context ):
        return 1

    IsDone = InitActivatedThread( context )

    if Config.IsPortalDebug:
        logger.info( '%s BeginThread class %s: %s' % ( thread_id, klass or 'Express Suite DMS', IsDone ) )
    return IsDone

def AbortThread( context ):
    """
        Aborts thread's transaction
    """
    if context is None:
        return
    for catalog in getZCatalogInstances( context ):
        if IsThreadActivated( catalog ):
            catalog._catalog.termThread()

def CommitActivatedThread( context, REQUEST=None ):
    """
        Performes catalog actions log
    """
    if context is None:
        return
    if REQUEST is None:
        REQUEST = aq_get( context, 'REQUEST', None )
        if REQUEST is None:
            return

    thread_id = get_ident()

    for catalog in getZCatalogInstances( context ):
        if IsThreadActivated( catalog ):
            catalog._catalog.commitThread( REQUEST )

    if Config.IsPortalDebug:
        logger.info( '%s CommitActivatedThread' % thread_id )

def CommitThread( context, klass=None, error=None, force=None, subtransaction=None, info=None, no_hook=0 ):
    """
        Finalizes thread's transaction
    """
    if not ( force or check_portal_settings( context ) ):
        return 1

    tts = transaction.get()

    if tts is None:
        logger.error( 'Utils.CommitThread transaction is broken, info: %s' % info, exc_info=True )
        return 1

    conflict_timeout = check_portal_settings( context, 'duration' ) or 0.1

    if error:
        AbortThread( context )
        IsDone = run_action_in_thread( 1, klass, error, subtransaction, info, conflict_timeout, tts )
    else:
        REQUEST = aq_get( context, 'REQUEST', None )

        if not no_hook:
            tts.beforeCommitHook( CommitActivatedThread, context, REQUEST )

        IsDone = run_action_in_thread( 1, klass, error, subtransaction, info, conflict_timeout, tts )

        if IsDone and no_hook:
            CommitActivatedThread( context, REQUEST=None )

        if REQUEST is None:
            pass
        elif IsDone:
            notify_after_commit = REQUEST.get('notify_after_commit', None)
            if notify_after_commit:
                for key in notify_after_commit.keys():
                    ob = _unrestrictedGetObjectByUid( context, key )
                    if ob is not None: # or force
                        if not notify_after_commit[ key ]:
                            if Config.IsPortalDebug:
                                logger.info( 'Utils.CommitThread notification item is empty: uid=[%s]' % key )
                        for method, args, kw in notify_after_commit[ key ]:
                            kw['no_commit'] = 1
                            kw['raise_exc'] = 1
                            try:
                                apply( method, args, kw )
                            except:
                                logger.error( 'Utils.CommitThread cannot notify after commit: uid=[%s], method: %s, thread_id: %s' % ( \
                                    key, callable(method) and method.__name__ or str(method), get_ident() ), \
                                    exc_info=True )
                                IsDone = -1
                    else:
                        logger.error( 'Utils.CommitThread object is None: uid=[%s]' % key )

                REQUEST.set('notify_after_commit', None)

    interrupt_thread( context, 1 )

    return IsDone

def check_conflictTimeout( conflict_timeout ):
    if conflict_timeout <= 0:
        x = 0
    elif conflict_timeout < 0.01:
        x = conflict_timeout * 1000
    elif conflict_timeout < 0.1:
        x = conflict_timeout * 100
    elif conflict_timeout <= 1:
        x = conflict_timeout * 10
    elif conflict_timeout <= 10:
        x = 1.0
    else:
        x = 0
    return x and float( x ) or 0

def run_action_in_thread( action, klass, error, subtransaction, info, conflict_timeout, tts ):
    """
        Run commit action
    """
    if not action or tts is None:
        return 1

    if info:
        message = '\n' + str(info)
    else:
        message = ''

    thread_id = get_ident()
    conflict_timeout = check_conflictTimeout( conflict_timeout )
    IsError = 0

    try:
        if error:
            action_in_thread = 'AbortThread'
        else:
            action_in_thread = 'CommitThread'
            tts.commit()

    except ConflictError:
        IsError = 1

    if error or IsError:
        tts.abort()

    if IsError:
        if subtransaction is None:
            if conflict_timeout > 0:
                threading.Event().wait( conflict_timeout )
        raise ConflictError

    if Config.IsPortalDebug:
        logger.info( '%s %s class %s, subtransaction %s%s' % ( \
            thread_id, action_in_thread, klass or 'Express Suite DMS', subtransaction, message ) )

    return not IsError and 1 or 0

def UpdateRequestRuntime( context, user, t1, t2, info ):
    """
        Update transaction request run-time
    """
    membership = getToolByName( context, 'portal_membership', None )
    if membership is None:
        return
    runtime = (t2 - t1) * 86400
    #portal_info( 'Utils.UpdateRequestRuntime', 'transaction run-time', ( user, t1, t2, runtime, info ) )
    membership.updateLoginTime( user, runtime, info )
    return

def interrupt_thread( context, force=0 ):
    """
        Make possible to start another thread
    """
    if not force and not check_portal_settings( context, 'use_timeout' ):
        return
    threading.Event().wait( float(check_portal_settings( context, 'duration' ) or 0.001 ) )

def check_portal_settings( context, name='apply_threading' ):
    """
        Checks the 'apply_threading' property settings
    """
    if context is None:
        return 0
    prptool = getToolByName( context, 'portal_properties', None )
    if prptool is None:
        return 0
    return prptool.getProperty(name)
