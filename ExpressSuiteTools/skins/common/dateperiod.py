## Script (Python) "dateperiod"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=period, short=None, lang='ru'
##title=
##
REQUEST = getattr( context, 'REQUEST', None )
if REQUEST:
    lang = REQUEST.get('LOCALIZER_LANGUAGE')

out = ''

try:
    days = period / 86400
    hours = ( period - days * 86400 ) / 3600
    minutes = ( period - days * 86400 - hours * 3600 ) / 60
except:
    days = hours = minutes = 0

if lang == 'ru' or not lang:
    if days > 0:
        out = out + "%d" % days
        if days < 1:
            out = ''
            hours=days * 86400 / 3600
        elif (days < 10 or days > 20) and int(days%10)==1:
            out = out + ' день '
        elif (days < 10 or days > 20) and int(days%10) in [2,3,4]:
            out = out + ' дня '
        else:
            out = out + ' дней '

        if short and out: return out

    if hours > 0:
        out = out + "%d" % hours
        if hours < 1:
            out = ''
            minutes=hours * 3600 / 60
        elif (hours < 10 or hours > 20) and int(hours%10)==1:
            out = out + ' час '
        elif (hours < 10 or hours > 20) and int(hours%10) in [2,3,4]:
            out = out + ' часа '
        else:
            out = out + ' часов '

        if short and out: return out

    if minutes > 0:
        out = out + "%d" % minutes
        if (minutes < 10 or minutes > 20) and int(minutes%10)==1:
            out = out + ' минута '
        elif (minutes < 10 or minutes > 20) and int(minutes%10) in [2,3,4]:
            out = out + ' минуты '
        else:
            out = out + ' минут '

        if short: return out
else:
    if days:
        out = out + '%d day(s) ' % days
        if short: return out

    if hours:
        out = out + '%d hour(s) ' % hours
        if short: return out

    if minutes:
        out = out + '%d minute(s) ' % minutes
        if short: return out

return out.strip()
