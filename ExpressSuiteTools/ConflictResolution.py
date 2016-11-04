"""
ConflictResolution Utilities
$Id: ConflictResolution.py, v 1.0 2008/09/19 12:00:00 Exp $

*** Checked 05/02/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from zLOG import LOG, DEBUG, INFO
from types import DictType, TupleType, ListType, StringType

from Globals import PersistentMapping

from logging import getLogger
logger = getLogger( 'ConflictResolution Utilities' )


def ResolveConflict( klass, oldState, savedState, newState, resolve_keys=None, update_local_roles=None, mode=None, 
                     trace=None, default=None ):
    """
        Resolving ZODB conflicts.

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

        'resolve_keys'       -- attr names to resolve, list

        'update_local_roles' -- Boolean, indicates if we should check 'local_roles' aatributes

        'mode'               -- resolution mode

        'trace'              -- trace mode

        'default'            -- return 'default' value if state differents is not checked.
    """
    def compare_items( x1, x2 ):
        if not None in ( x1, x2, ) and type(x1) == type(x2):
            if type(x1) not in ( DictType, TupleType, ListType, StringType, ):
                return 0
            return x1 > x2 and 1 or x2 > x1 and 2 or 0
        return None

    def valid_items( x ):
        if x is None: return None
        t = type(x)
        return t in ( DictType, PersistentMapping, ) and len(x.keys()) or \
               t in ( ListType, TupleType ) and len(x) or \
               0

    if type(resolve_keys) is StringType:
        resolve_keys = [resolve_keys]

    if mode == -1:
        # Compare states and print the difference
        # ---------------------------------------
        states = ( oldState, savedState, newState, )
        values = [ [], [], [] ]
        has_difference = 0

        for key in resolve_keys:
            s = []
            for i in (0,1,2):
                state = states[i]
                x = state and state.get(key, None) or None
                if x and x not in s:
                    has_difference = 1
                    s.append(x)
                values[i].append(x)

        if has_difference and trace:
            for i, state in ( ( 's', savedState, ), ( 'n', newState, ), ):
                for id in state.keys():
                    x = state[id]
                    if not oldState.has_key(id):
                        LOG('%s.ResolveConflict' % klass, INFO, 'id: %s (item not found)\n%s: %s' % ( \
                            id, i, str(x) ) )
                    else:
                        p = compare_items( x, oldState[id] )
                        if not p:
                            continue
                        LOG('%s.ResolveConflict' % klass, INFO, 'id: %s (not equal), p: %s\n%s: %s\no: %s' % ( \
                            id, p, i, str(x), str(oldState[id]) ) )

        if has_difference:
            resolved = values.index(max(values))
            LOG('%s.ResolveConflict' % klass, DEBUG, 'states for keys: %s, resolved: %s\n%s' % ( \
                str(resolve_keys), resolved, '\n'.join([ str(x) for x in values ]) ) )
            return states[resolved]

        return default

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
            # Mapping items (MemberActiviry, MemberProperties)
            # ------------------------------------------------
            if valid_saved and valid_new and valid_old >= 0:
                for x in ( saved, new, ):
                    for id in x.keys():
                        if not old.has_key(id):
                            old[id] = x[id]
                            continue
                        try:
                            if compare_items( x[id], old[id] ) == 1:
                                old[id] = x[id]
                        except KeyError:
                            pass
            else:
                x = max( valid_old, valid_saved, valid_new )
                if x > 0:
                    LOG('%s.ResolveConflict' % klass, DEBUG, 'objects are not consistent: %s, key [%s]' % ( \
                        x, key ))
                    if x == valid_new:
                        old = new
                    elif x == valid_saved:
                        old = saved
                else:
                    LOG('%s.ResolveConflict' % klass, DEBUG, 'error resolve key [%s], type %s, x:%s' % ( \
                        key, type(oldState), x ))
                    raise ConflictError

            oldState[key] = old
            x = len(old.keys())

        elif mode == 1:
            # Mapping container (Heading, GuardedTable, MailServerBase)
            # ---------------------------------------------------------
            resolved = list(old)

            # check appended objects
            old_keys = oldState.keys()
            ids = []

            for state in ( savedState, newState, ):
                for x in state[key]:
                    id = x.get('id')
                    if id and not ( id in ids or id in old_keys ):
                        oldState[id] = state[id]
                        resolved.append( x )
                        ids.append( id )

                if update_local_roles:
                    try:
                        oldState['__ac_local_roles__'].update(state['__ac_local_roles__'])
                        oldState['__ac_local_group_roles__'].update(state['__ac_local_group_roles__'])
                    except: pass

            # check removed objects
            if valid_old > min(valid_saved, valid_new):
                saved_keys = savedState.keys()
                new_keys = newState.keys()
                for x in old:
                    id = x.get('id')
                    if id and not ( id in saved_keys and id in new_keys ):
                        del oldState[id]
                        resolved.remove( x )
                del saved_keys, new_keys

            oldState[key] = tuple(resolved)
            x = len(resolved)

            del old_keys, ids

        elif mode == 2:
            # Mapping objects (TaskItemContainer, GuardedEntry, Link, Schedule)
            # -----------------------------------------------------------------
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