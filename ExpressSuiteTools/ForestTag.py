"""
Rendering object hierarchies as Trees multiple tags per page possible.
Tags on serveral pages may share status.

$Id: ForestTag.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 06/06/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from zLOG import LOG, ERROR, DEBUG, INFO

from string import join, split, rfind, find, translate, replace
from urllib import quote, unquote
from zlib import compress, decompress
from binascii import b2a_base64, a2b_base64

from DocumentTemplate.DT_Util import *
from DocumentTemplate.DT_String import String

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName

from TreeDisplay.TreeTag import tpRenderTABLE, encode_str, tpValuesIds, oid, \
     tpStateLevel, apply_diff #, encode_seq, decode_seq

from CustomDefinitions import PortalInstance

tbl=join(map(chr, range(256)),'')
tplus=tbl[:ord('+')]+'-'+tbl[ord('+')+1:]
tminus=tbl[:ord('-')]+'+'+tbl[ord('-')+1:]


def _IsDebug( context ):
    return context.getPortalObject().aq_parent.getProperty('DEBUG_ForestTag')

class Forest:
    name = 'forest'
    blockContinuations = ()
    expand = None

    def __init__( self, blocks ):
        tname, args, section = blocks[0]
        args=parse_params( args, name=None, expr=None, nowrap=1,
                           expand=None, leaves=None, code=None,
                           header=None, footer=None,
                           branches=None, branches_expr_root=None, branches_expr=None, ext_params=None,
                           sort=None, reverse=1, skip_unauthorized=1,
                           id=None, single=1, url=None,
                           secured_tree=None,
                           content_filter=None,
                           # opened_decoration=None,
                           # closed_decoration=None,
                           # childless_decoration=None,
                           assume_children=1,
                           urlparam=None, prefix=None,
                           state_id=None,
                           state_url=None,
                           security=None, security_expr=None,
                           pl_icon=None,
                           mi_icon=None )
        has_key = args.has_key

        if has_key('') or has_key('name') or has_key('expr'):
            name,expr = name_param(args,'tree',1)
            if expr is not None: args['expr']=expr
            elif has_key(''): args['name']=name
        else:
            name = 'a tree tag'

        if has_key('branches_expr_root'):
            args['branches_expr_root'] = Eval(args['branches_expr_root']).eval

        if has_key('branches_expr'):
            if has_key('branches'):
                raise ParseError, _tm('branches and branches_expr given', 'tree')
            args['branches_expr'] = Eval(args['branches_expr']).eval
        elif not has_key('branches'):
            args['branches'] = 'tpValues'

        if has_key('security_expr'):
            if has_key('security'):
                raise ParseError, _tm('security and security_expr given', 'tree')
            args['security_expr'] = Eval(args['security_expr']).eval

        if has_key('ext_params'):
            args['ext_params'] = Eval(args['ext_params']).eval

        if not has_key('id'): args['id'] = 'tpId'
        if not has_key('url'): args['url'] = 'tpURL'
        if not has_key('childless_decoration'): args['childless_decoration'] = ''

        prefix = args.get('prefix')
        if prefix and not simple_name(prefix):
            raise ParseError, _tm('prefix is not a simple name', 'tree')

        if not has_key('state_id'): args['state_id'] = 'forest'
        if not has_key('state_url'): args['state_url'] = '/'

        self.__name__ = name
        self.section = section.blocks
        self.args = args

    def render( self, md ):
        args=self.args
        have=args.has_key

        if have('name'): v = md[args['name']]
        elif have('expr'): v = args['expr'].eval(md)
        else: v = md.this
        return tpRender( v, md, self.section, self.args )

    __call__ = render

    def tpSecureValues(self):
        # Return a list of subobjects, used by tree tag.
        r=[]
        if hasattr(aq_base(self), 'tree_ids'):
            tree_ids=self.tree_ids
            try: tree_ids = list(tree_ids)
            except TypeError:
                pass
            if hasattr(tree_ids, 'sort'):
                tree_ids.sort()
            for id in tree_ids:
                if hasattr(self, id):
                    r.append(self._getOb(id))
        else:
            obj_ids=self.objectIds()
            obj_ids.sort()
            for id in obj_ids:
                o=self._getOb(id)
                if hasattr(o, 'isPrincipiaFolderish') and \
                   o.isPrincipiaFolderish:
                    r.append(o)
        return r

String.commands['forest']=Forest

pyid=id # Copy builtin

def tpRender( self, md, section, args, s_type=None ):
    """
        Render data organized as a tree.

        We keep track of open nodes using a cookie.  The cookie stored the
        tree state. State should be a tree represented like:

          []  # all closed
          ['eagle'], # eagle is open
          ['eagle'], ['jeep', [1983, 1985]]  # eagle, jeep, 1983 jeep and 1985 jeep

        where the items are object ids. The state will be converted to a
        compressed and base64ed string that gets unencoded, uncompressed,
        and evaluated on the other side.

        Note that ids used in state need not be connected to urls, since
        state manipulation is internal to rendering logic.

        Note that to make eval safe, we do not allow the character '*' in
        the state.

        Multiple tags per page are possible.
        Multiple tags on different pages may share same state.
    """
    if s_type is None:
        simple_type = {type(''):0, type(1):0, type(1.0):0}.has_key
    else:
        simple_type = s_type

    #IsDebug = _IsDebug( self )

    data = []
    idattr = args['id']

    if hasattr(self, idattr):
        id = getattr(self, idattr)
        if not simple_type(type(id)):
            id = id()
    elif hasattr(self, '_p_oid'):
        id = oid(self)
    else:
        id = pyid(self)

    try:
        # see if we are being run as a sub-document
        root = md['tree-root-url']
        url = md['tree-item-url']
        state = md['tree-state']
        diff = md['tree-diff']
        substate = md['-tree-substate-']
        colspan = md['tree-colspan']
        level = md['tree-level']

    except KeyError:
        # OK, we are a top-level invocation
        level = -1
        expand = collapse = None

        if md.has_key('collapse_all'):
            state = [id,[]],
        elif md.has_key('expand_all'):
            have_arg = args.has_key
            if have_arg('branches'):
                def get_items( node, branches=args['branches'], md=md ):
                    get = md.guarded_getattr
                    if get is None:
                        get = getattr
                    items = get(node, branches)
                    return items()
            elif have_arg('branches_expr'):
                def get_items( node, branches_expr=args['branches_expr'], md=md ):
                    md._push(InstanceDict(node, md))
                    items = branches_expr(md)
                    md._pop()
                    return items
            state = [id, tpValuesIds(self, get_items, args)],
        else:
            if md.has_key('tree-s' + args['state_id']):
                state = md['tree-s' + args['state_id']]
                #LOG('1', DEBUG, 'state: %s, id: %s' % ( state, id ) )
                state = decode_seq(state)
                #LOG('2', DEBUG, 'state: %s' % state )
                try:
                    if state[0][0] != id:
                        state = [id,[]],
                        #LOG('3', DEBUG, 'state: %s' % state )
                except IndexError:
                    state = [id,[]],
                    #LOG('4', DEBUG, 'state: %s' % state )
            else:
                state = [id,[]],
                #LOG('5', DEBUG, 'state: %s' % state )

            #if IsDebug:
            #    LOG('ForestTag.tpRender', DEBUG, 'state: %s' % state )

            if md.has_key('tree-e'):
                diff = decode_seq(md['tree-e'])
                apply_diff(state, diff, 1)
                expand = md['tree-e']

            if md.has_key('tree-c'):
                diff = decode_seq(md['tree-c'])
                apply_diff(state, diff, 0)
                collapse = md['tree-c']

        colspan = tpStateLevel(state)
        substate = state
        diff = []

        url = ''
        root = md['URL']
        l = rfind(root,'/')
        if l >= 0: root = root[l+1:]

    treeData = {'tree-root-url': root, 'tree-colspan': colspan, 'tree-state': state }

    #if IsDebug:
    #    LOG('ForestTag.tpRender', DEBUG, 'treeData: %s, expand: %s, collapse: %s' % ( \
    #        str(treeData), expand, collapse ))

    prefix = args.get('prefix')
    if prefix:
        for k, v in treeData.items():
            treeData[prefix + replace(k[4:], '-', '_')] = v

    md._push(InstanceDict(self, md))
    md._push(treeData)

    try: tpRenderTABLE( self, id, root, url, state, substate, diff, data, colspan,
                        section, md, treeData, level, args )
    finally: md._pop(2)

    if state is substate and not ( args.has_key('single') and args['single'] ):
        state = state or ([id],)
        state = encode_seq(state)
        md['RESPONSE'].setCookie('tree-s' + args['state_id'], state, path=args['state_url'])
    return join(data,'')

def tpRenderTABLE( self, id, root_url, url, state, substate, diff, data,
                   colspan, section, md, treeData, level=None, args=None,
                   s_type=None ):
    "Render a tree as a table"
    if level is None:
        level = 0
    if s_type is None:
        simple_type = {type(''):0, type(1):0, type(1.0):0}.has_key
    else:
        simple_type = s_type

    #IsDebug = _IsDebug( self )

    have_arg = args.has_key
    exp = 0

    if level >= 0:
        urlattr = args['url']
        if urlattr and hasattr(self, urlattr):
            tpUrl = getattr(self, urlattr)
            if not simple_type(type(tpUrl)):
                tpUrl=tpUrl()
            url = (url and ('%s/%s' % (url, tpUrl))) or tpUrl
            root_url = root_url or tpUrl

    ptreeData = add_with_prefix( treeData, 'tree', args.get('prefix') )
    ptreeData['tree-item-url'] = url
    ptreeData['tree-level'] = level
    ptreeData['tree-item-expanded'] = 0
    ptreeData['tree-item-code'] = 0
    idattr = args['id']

    children = have_arg('assume_children') and args['assume_children']

    #if IsDebug:
    #    LOG('ForestTag.tpRenderTABLE', DEBUG, 'ptreeData: %s, level: %s, chidren: %s' % ( \
    #        str(ptreeData), level, children ))

    output = data.append

    if ( children and substate is not state ):
        # We should not compute children unless we have to.
        # See if we've been asked to expand our children.
        for i in range(len(substate)):
            sub = substate[i]
            if sub[0] == id:
                exp = i+1
                break
        if not exp: items = 1

    get = md.guarded_getattr
    if get is None:
        get = getattr

    items = None
    IsPortalRoot = have_arg('branches_expr_root') and self.implements('isPortalRoot')

    if items is None:
        if have_arg('branches') and hasattr(self, args['branches']):
            items = get(self, args['branches'])
            items = items()
        elif IsPortalRoot:
            items = args['branches_expr_root'](md)
        elif have_arg('branches_expr'):
            #LOG('ForestTag.tpRenderTABLE', INFO, 'expr: %s' % callable(args['branches_expr']))
            #LOG('ForestTag.tpRenderTABLE', INFO, 'implements: %s' % self.implements())
            #LOG('ForestTag.tpRenderTABLE', INFO, 'url: %s-%s' % (root_url, url))
            items = args['branches_expr'](md)

        if have_arg('content_filter'):
            ids = [ item.id for item in items ]
            items = map( lambda item: item[1], self._filteredItems( ids, eval(args['content_filter']) ) )

        if not items and have_arg('leaves'):
            items = 1

    #if IsDebug:
    #    LOG('ForestTag.tpRenderTABLE', DEBUG, 'id: %s, items: %s' % ( id, str(items) ))

    if items and items != 1:
        getitem = getattr(md, 'guarded_getitem', None)
        if getitem is not None:
            unauth = []
            secured = None
            security = None

            while secured is None:
                secured = 1
                for index in range(len(items)):
                    md._push(InstanceDict(items[index], md))

                    if have_arg('security') and hasattr(items[index], args['security']):
                        security = get(items[index], args['security'])
                        security = security()
                    elif have_arg('security_expr'):
                        security = args['security_expr'](md)
                    else:
                        security = 1

                    try:
                        if not security:
                            if have_arg('branches') and hasattr(self, args['branches']):
                                subitems = get(items[index], args['branches'])
                                subitems = subitems()
                            elif have_arg('branches_expr'):
                                subitems=args['branches_expr'](md)

                            del items[index]

                            items += subitems
                            secured = None
                            md._pop()
                            break
                    except ValidationError:
                        unauth.append(index)

                    md._pop()

                    if unauth:
                        if have_arg('skip_unauthorized') and args['skip_unauthorized']:
                            items = list(items)
                            unauth.reverse()
                            for index in unauth:
                                del items[index]
                        else:
                            raise ValidationError, unauth

        if have_arg('sort') and items:
            # Faster/less mem in-place sort
            if type(items) == type(()):
                items = list(items)
            sort = args['sort']
            x = getattr( items[0], sort, None )
            if x and callable( x ):
                size = range(len(items))
                for i in size:
                    v = items[i]
                    k = getattr( v, sort )
                    try: k = k()
                    except: pass
                    items[i] = ( k,v )
                items.sort()
                for i in size:
                    items[i] = items[i][1]
            else:
                try: items.sort( lambda x, y, sort=sort: cmp(x[sort], y[sort]) )
                except: pass

            if have_arg('reverse') and IsPortalRoot:
                items.reverse()

    diff.append( id )

    _td_colspan = '<TD COLSPAN="%s" NOWRAP>&nbsp;</TD>'
    _td_single  = '<TD WIDTH="16" NOWRAP><img src="spacer.gif" width="16" height="1"></TD>'

    #if IsDebug:
    #    LOG('ForestTag.tpRenderTABLE', DEBUG, 'substate: %s, state: %s, items: %s, level: %s' % ( \
    #        substate, state, items, level ))

    sub = None
    if substate is state:
        output('<TABLE CELLSPACING="0">\n')
        sub = substate[0]
        exp = items
    else:
        # Add prefix
        output('<TR>\n')
        # Add +/- icon
        if items:
            if level:
                if level > 3: output(_td_colspan % (level-1))
                elif level > 1: output(_td_single * (level-1))
                output(_td_single)
                output('\n')
            output('<TD WIDTH="16" VALIGN="TOP" NOWRAP style="padding-top:8px">')
            for i in range(len(substate)):
                sub = substate[i]
                if sub[0] == id:
                    exp = i+1
                    break

            ####################################
            # Mostly inline encode_seq for speed
            s = compress(str(diff))
            if len(s) > 57: s=encode_str(s)
            else:
                s = b2a_base64(s)[:-1]
                l = find(s,'=')
                if l >= 0: s=s[:l]
            s = translate(s, tplus)
            ####################################

            script = md['SCRIPT_NAME']

            # Propagate extra args through tree.
            if args.has_key( 'urlparam' ):
                param = args['urlparam']
                param = "%s&" % param
            else:
                param = ""

            try:
                ps = PortalInstance( self )
                common_url = ps['common']
            except:
                common_url = None

            if have_arg('mi_icon'):
                mi_icon = args['mi_icon']
            elif common_url:
                mi_icon = common_url + '/mi.gif'
            else:
                mi_icon = script + '/p_/mi'

            if have_arg('pl_icon'):
                pl_icon = args['pl_icon']
            elif common_url:
                pl_icon = common_url + '/pl.gif'
            else:
                pl_icon = script + '/p_/pl'

            ext_params = have_arg('ext_params') and '%s&' % args['ext_params'](md) or ''

            if exp:
                ptreeData['tree-item-expanded']=1
                output('<a href="%s?%s%stree-c=%s#%s">'
                       '<img src="%s" alt="-" border=0></a>' %
                       (root_url, param, ext_params, s, id, mi_icon))
            else:
                output('<a href="%s?%s%stree-e=%s#%s">'
                       '<img src="%s" alt="+" border=0></a>' %
                       (root_url, param, ext_params, s, id, pl_icon))

            ptreeData['tree-item-code']=s
            output('</TD>\n')

        else:
            if level > 2: output(_td_colspan % level)
            elif level > 0: output(_td_single  * level)
            output(_td_single)
            output('\n')

        # add item text
        dataspan = colspan-level
        output('<TD%s%s VALIGN="TOP" ALIGN="LEFT" STYLE="WIDTH:%s;">' %
               ((dataspan > 1 and (' COLSPAN="%s"' % dataspan) or ''),
                (have_arg('nowrap') and args['nowrap'] and ' NOWRAP' or ''),
                '100%')
              )
        output(render_blocks(section, md))
        output('</TD>\n</TR>\n')

    #if IsDebug:
    #    LOG('ForestTag.tpRenderTABLE', DEBUG, 'exp: %s' % exp)

    if exp:
        level = level+1
        dataspan = colspan-level
        if level > 2:
            h=_td_colspan % level
        elif level > 0:
            h=_td_single * level
        else:
            h=''

        if have_arg('header'):
            doc = args['header']
            if md.has_key(doc):
                doc = md.getitem(doc,0)
            else:
                doc=None
            if doc is not None:
                output(doc(
                    None, md,
                    standard_html_header=(
                        '<TR>%s<TD WIDTH="16" NOWRAP></TD>'
                        '<TD%s VALIGN="TOP">'
                        % (h,
                           (dataspan > 1 and (' COLSPAN="%s"' % dataspan)
                            or ''))),
                    standard_html_footer='</TD></TR>',
                    ))

        if items == 1:
            # leaves
            if have_arg('leaves'):
                doc = args['leaves']
                if md.has_key(doc):
                    doc = md.getitem(doc,0)
                else:
                    doc = None
                if doc is not None:
                    treeData['-tree-substate-'] = sub
                    ptreeData['tree-level'] = level
                    md._push(treeData)
                    try: output(doc(
                        None,md,
                        standard_html_header=(
                            '<TR>%s<TD WIDTH="16" NOWRAP></TD>'
                            '<TD%s VALIGN="TOP">'
                            % (h,
                               (dataspan > 1 and
                                (' COLSPAN="%s"' % dataspan) or ''))),
                        standard_html_footer='</TD></TR>',
                        ))
                    finally: md._pop(1)
        elif have_arg('expand'):
            doc = args['expand']
            if md.has_key(doc):
                doc = md.getitem(doc,0)
            else:
                doc = None
            if doc is not None:
                treeData['-tree-substate-'] = sub
                ptreeData['tree-level'] = level
                md._push(treeData)
                try: output(doc(
                    None,md,
                    standard_html_header=(
                        '<TR>%s<TD WIDTH="16" NOWRAP></TD>'
                        '<TD%s VALIGN="TOP">'
                        % (h,
                           (dataspan > 1 and
                            (' COLSPAN="%s"' % dataspan) or ''))),
                    standard_html_footer='</TD></TR>',
                    ))
                finally: md._pop(1)
        else:
            __traceback_info__ = sub, args, state, substate
            ids = {}
            for item in items:
                if hasattr(item, idattr):
                    id = getattr(item, idattr)
                    if not simple_type(type(id)):
                        id = id()
                elif hasattr(item, '_p_oid'):
                    id = oid(item)
                else:
                    id = pyid(item)
                if len(sub) == 1:
                    sub.append([])
                substate = sub[1]
                ids[id] = 1
                md._push(InstanceDict(item, md))
                try: data = tpRenderTABLE( item, id, root_url, url, state, substate, diff, data, \
                                           colspan, section, md, treeData, level, args)
                finally: md._pop()
                if not sub[1]: del sub[1]

            ids = ids.has_key
            for i in range(len(substate)-1,-1):
                if not ids(substate[i][0]):
                    del substate[i]

        if have_arg('footer'):
            doc = args['footer']
            if md.has_key(doc):
                doc = md.getitem(doc,0)
            else:
                doc = None
            if doc is not None:
                output(doc(
                    None, md,
                    standard_html_header=(
                        '<TR>%s<TD WIDTH="16" NOWRAP></TD>'
                        '<TD%s VALIGN="TOP">'
                        % (h,
                           (dataspan > 1 and (' COLSPAN="%s"' % dataspan)
                            or ''))),
                    standard_html_footer='</TD></TR>',
                    ))

    del diff[-1]
    if not diff: output('</TABLE>\n')

    return data

tpSecureValues=Forest.tpSecureValues

#icoSpace='<IMG SRC="Blank_icon" BORDER="0">'
#icoPlus ='<IMG SRC="Plus_icon" BORDER="0">'
#icoMinus='<IMG SRC="Minus_icon" BORDER="0">'


def encode_seq(state):
    "Convert a sequence to an encoded string"
    state=compress(str(state))
    l=len(state)

    if l > 57:
        states=[]
        for i in range(0,l,57):
            states.append(b2a_base64(state[i:i+57])[:-1])
        state=''.join(states)
    else: state=b2a_base64(state)[:-1]

    l=state.find('=')
    if l >= 0: state=state[:l]

    state=translate(state, tplus)
    return state

def decode_seq(state):
    "Convert an encoded string to a sequence"
    state=translate(state, tminus)
    l=len(state)

    if l > 76:
        states=[]
        j=0
        for i in range(l/76):
            k=j+76
            states.append(a2b_base64(state[j:k]))
            j=k

        if j < l:
            state=state[j:]
            l=len(state)
            k=l%4
            if k: state=state+'='*(4-k)
            states.append(a2b_base64(state))
        state=''.join(states)
    else:
        l=len(state)
        k=l%4
        if k: state=state+'='*(4-k)
        state=a2b_base64(state)

    state=decompress(state)
    if state.find('*') >= 0: raise 'Illegal State', state
    try: return list(eval(state,{'__builtins__':{}}))
    except: return []
