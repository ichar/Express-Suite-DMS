"""
Portal Scheduler. Utils functions
$Id: Utils.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 12/10/2008 ***

"""
__version__ = "$Revision: 1.0 $"[11:-2]

import sys, re
from types import DictType, TupleType, ListType, StringType
from zLOG import LOG, INFO, DEBUG, ERROR

from AccessControl.SecurityManagement import get_ident
from Products.CMFCore.utils import getToolByName

SequenceTypes = ( TupleType, ListType )


def ResolveConflict( klass, oldState, savedState, newState, resolve_keys, mode=None ):
    """
        Resolving Conflicts.

        The method should return the state of the object after resolving the differences.

        'klass'              -- Class name.

        'oldState'           -- The state of the object that the changes made by the current transaction were based on.
                                The method is permitted to modify this value.
                                *old*

        'savedState'         -- The state of the object that is currently stored in the database.
                                This state was written after oldState and reflects changes made by a transaction
                                that committed before the current transaction.
                                The method is permitted to modify this value.
                                *committed*

        'newState'           -- The state after changes made by the current transaction.
                                This method should compute a new state by merging changes reflected in savedState 
                                and newState, relative to oldState.
                                The method is not permitted to modify this value.
                                *new*

        'resolve_keys'       -- attr names to resolve, list.

        'mode'               -- resolution mode.

    """
    def valid_items( x ):
        if x is None: return None
        t = type(x)
        return t in ( DictType, ) and len(x.keys()) or \
               t in ( ListType, TupleType ) and len(x) or \
               0

    if type(resolve_keys) is StringType:
        resolve_keys = [resolve_keys]

    LOG('%s.ResolveConflict' % klass, DEBUG, 'tries to resolve conflict: class [%s], keys %s' % ( \
        klass, resolve_keys ))

    for key in resolve_keys:
        old = None
        saved = None
        new = None

        try:
            old = oldState.get(key)
            saved = savedState.get(key)
            new = newState.get(key)
        except:
            LOG('%s.ResolveConflict' % klass, DEBUG, 'type %s, resolved key [%s]' % ( sys.exc_type, key ) )
            raise

        valid_old = valid_items(old)
        valid_saved = valid_items(saved)
        valid_new = valid_items(new)

        if not mode:
            return oldState

        elif mode == 2:
            # Mapping objects (Schedule)
            # --------------------------
            try:
                old = old.copy()
                resolved = list(old.keys())
            except:
                if not valid_old:
                    raise

            # appended objects
            for state in ( saved, new, ):
                for id, ob in state.items():
                    if id not in resolved:
                        oldState[key][id] = ob
                        resolved.append( id )

            # removed objects
            if valid_old > min(valid_saved, valid_new):
                for id in old.keys():
                    if not ( id in saved.keys() and id in new.keys() ):
                        del oldState[key][id]
                        resolved.remove( id )

            x = len(resolved)

        LOG('%s.ResolveConflict' % klass, DEBUG, \
            'items: old %s, saved %s, new %s, resolved: %s, key [%s], mode: %s' % ( \
            valid_old, valid_saved, valid_new, x, key, mode ))

    return oldState

_bad_id_re = re.compile( r'[^a-zA-Z0-9-_~$# ]+' )

def cookId( container, id=None, mask=None, prefix='', suffix='', idx=0, title=None, size=20 ):
    """
        Generates a new object identifier, the best of all possible
    """
    if hasattr( container, '_checkId' ):
        check_id = container._checkId
    else:
        assert hasattr( container, 'has_key' ), "invalid container type"
        def check_id( id, container=container ):
            if container.has_key(id):
                raise DuplicateIdError

    if not prefix:
        pass
    elif prefix == '_authenticated_':
        try: username = getToolByName( context, 'portal_membership' ).getAuthenticatedMember().getUserName()
        except: username = ''
        id = ( mask or '%s_%s_%s' ) % ( strftime( '%Y%m%d%H%M%S', localtime() ), username, id )
        prefix = None
    elif prefix == '_localtime_':
        id = ( mask or '%s_%s' ) % ( strftime( '%m%d%H%M%S', localtime() ), id )
        prefix = None
    elif prefix == '_thread_':
        id = ( mask or '%s_%s' ) % ( get_ident(), idx )
        prefix = None

    if id:
        try:
            check_id( id )
        except DuplicateIdError:
            if not prefix:
                prefix = id
            id = None
        except InvalidIdError:
            id = None
        else:
            if not prefix:
                prefix = id

    elif prefix:
        prefix = _bad_id_re.sub( '_', prefix )

    while not id:
        if prefix:
            if prefix in ['entry']:
                idx += 1
                id = '%s_%05d%s' % ( prefix, idx, suffix )
            else:
                idx += 1
                id = '%s_%03d%s' % ( prefix, idx, suffix )

        else:
            id = 'obj%010u' % ( randrange(1000000000) )

        try: check_id( id )
        except ( DuplicateIdError, BadRequestException ): id = None

    return id
