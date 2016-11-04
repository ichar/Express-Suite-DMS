## Script (Python) "catalog_filter"
##parameters=
##title=Save table filter settings
##
from Products.ExpressSuiteTools.SecureImports import parseString, parseDate, \
     GetSessionValue, SetSessionValue, addQueryString
from string import split

REQUEST = context.REQUEST
r = REQUEST.get

filter_id = r('filter_id')
default_filter = { 'conditions':[], 'query':{} }

filter_map = GetSessionValue( context, '%s_filter' % filter_id, default_filter, REQUEST )

if not ( filter_map.has_key('conditions') and filter_map.has_key('query') ):
    filter_map = default_filter.copy()

conditions = filter_map.get('conditions')
query = filter_map.get('query')

if r('apply_filter'):
    for c in r('selected_conditions', []):
        if c and c not in conditions:
            conditions.append(c)
if not conditions:
    pass
else:
    for c in r('remove_conditions', '').strip().split(' '):
        if c in conditions:
            conditions.remove(c)
        try:
            del query[c]
        except:
            pass

if not conditions and query:
    conditions = query.keys()
empty = []

# Construct query
for id in conditions:
    if not id:
        empty.append( id )
        continue

    column_type = r('%s_column_type' % id) or ''
    operator = r('%s_operator' % id) or ''
    range = r('%s_range' % id) or ''

    if column_type == 'date':
        min_date = parseDate( 'filter_min_%s' % id, REQUEST, DateTime() )
        max_date = parseDate( 'filter_max_%s' % id, REQUEST, DateTime() )
        if min_date == max_date:
            max_date += 1
        value = ( min_date, max_date )
        operator = None
        range = 'min:max'

    elif column_type == 'boolean':
        if r('filter_'+id):
            value = 1
        else:
            value = 0

    elif column_type == 'items':
        value = r('filter_'+id, [])
        if value == ['nonselected']:
            value = None

    elif column_type in ('string', 'text'):
        value = r('filter_'+id, '')
        if value:
            if same_type(value, [], ()):
                value = value[0]
            value = parseString( value )
            if value and '%' not in value:
                value = '%' + value + '%'
        range = operator = None

    else:
        value = r('filter_'+id, '')

    if same_type(value, [], ()):
        if operator == 'OR': operator = None
        if len(value) > 100: value = value[0:99]

    if value:
        if range or operator:
            query[id] = { 'query' : value }
            if operator:
                query[id]['operator'] = operator
            if range:
                query[id]['range'] = range
        else:
            query[id] = value
    else:
        empty.append( id )

for id in empty:
    conditions.remove( id )
    try:
        del query[id]
    except:
        pass

filter_map['conditions'] = conditions
filter_map['query'] = query

SetSessionValue( context, '%s_filter' % filter_id, filter_map, REQUEST )
url = addQueryString( r('HTTP_REFERER'), {'qs':1} )

REQUEST['RESPONSE'].redirect( url )

