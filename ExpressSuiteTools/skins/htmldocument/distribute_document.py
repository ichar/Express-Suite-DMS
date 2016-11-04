## Script (Python) "send_notification"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters= subject, holding=''
##title=
##
REQUEST = context.REQUEST

lang = REQUEST.get('LOCALIZER_LANGUAGE')

transport = REQUEST.get( 'transport' )
requested_users = REQUEST.get('requested', [])
comment = REQUEST.get('comment')
letter_parts = REQUEST.get('letter_parts', [])
holding_emails = REQUEST.get('holding')
fax_numbers = REQUEST.get( 'fax_numbers', '' ).split(';')
return_receipt_to = REQUEST.get('return_receipt_to')
confirm_reading_to = REQUEST.get('confirm_reading_to')

if holding_emails:
    requested_users.extend( holding_emails )

other_user_emails = REQUEST.get('other_user_emails')

if other_user_emails:
    other = filter(None, [ x.strip() for x in other_user_emails.split(';') ])
    if other:
        requested_users.extend( other )

count = -1

if requested_users:
    count = context.distributeDocument( 'distribute_document_template'
                          , transport
                          , mto=requested_users
                          , subject=subject
                          , from_member=1
                          , REQUEST=REQUEST
                          , lang=lang
                          , letter_parts=letter_parts
                          , fax_numbers=fax_numbers
                          , comment=comment
                          , return_receipt_to=return_receipt_to
                          , confirm_reading_to=confirm_reading_to
                          , raise_exc=1
                          )

if count > 0:
    message = 'The document is distributed'
elif count == -1:
    message = 'The document was not distributed. Please check requested addresses $ $ error'
else:
    message = 'The document was not distributed $ $ error'

context.redirect( message=message )
