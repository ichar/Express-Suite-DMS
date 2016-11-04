//
// Registers callback for an event.
//
// Arguments:
//
//     'object' -- object on which to watch for events
//     'type' -- name of the event, with 'on' prefix
//     'callback' -- callback function object
//     'retval' -- required callback result (optional)
//
// Additional arguments are passed to the callback function as-is.
//
// Result:
//
//     Queue entry Id (actually, the callback's ordinal
//     number in the callbacks queue for this event).
//
function registerCallback( object, type ) {
    type = type.toLowerCase();
    object[ type ] = runCallbacks;

    var items = object[ type+'__callbacks__' ];
    if (items == null)
        items = object[ type+'__callbacks__' ] = new Array();

    var id = items.length;
    items[ id ] = toArray(arguments, 2);

    return id;
}
//
// Removes callback from then event queue.
//
// Arguments:
//
//     'object', 'type' -- as per 'registerCallback'
//     'id' -- queue entry Id received from 'registerCallback'
//
function unregisterCallback( object, type, id ) {
    type = type.toLowerCase();
    var items = object[ type+'__callbacks__' ];

    if (items && items.length > id)
        items[ id ] = null;
}
//
// Executes registered callbacks.
//
// The first argument of the function is the object that fired
// the event, the second is current Event object, and the rest
// are custom arguments passed to callback registration.
//
// The callback function is called with 'this' set to the object
// that fired the event (XXX does not work in MSIE 5.0).
//
// If 'retval' was specified and the return value of the function
// differs from it, the callbacks queue processing is interruptted
// and that value is returned as a result if the event handler.
//
function runCallbacks( event, object ) {
    if (object == null)
        object = this;

    var win = object.window || getDocument(object).parentWindow;
    var type, error;

    // determine event type
    if (typeof(event) == 'string') {
        type = event.toLowerCase();
        event = null;
    } else {
        event = event || win.event;
        type = 'on' + event.type.toLowerCase()
    }

    // get queue of the registered callbacks
    var items = object[ type+'__callbacks__' ];
    if (items == null) {
        // try to run ordinary js callback
        var callback = object[ type ];
        if (! callback)
            return true;
        return callback.apply( object, new Array(event) );
    }

    for (var i = 0; i < items.length; i++) {
        // item is [ callback, retval, args... ]
        var item = items[i];
        if (! item)
            continue; // was unregistered

        // build arguments list
        // NB: slice method in IE snaps on arrays
        //     from unloaded documents, so the loop is used
        var args = new Array( event );
        for (var j = 2; j < item.length; j++)
            args[ args.length ] = item[j];

        // now run the callback function
        var callback = item[0];
        var retval;
        try { retval = callback.apply( object, args ); }
        catch (error) {
            if( error.number == -2146823277 ) {
                // the script was unloaded (MSIE)
                items[i] = null;
                continue;
            }
            //throw error;
        }

        // check return value
        var wanted = item[1];
        if (wanted != null && retval != wanted)
            return retval;
    }
    return true;
}
//
// Registers onSubmit callback for a given form.
//
// Arguments:
//
//    'name' -- form's name
//    'callback' -- callback function object
//    'retval' -- required callback result or 'null'
//
// Additional arguments are passed to the callback as-is.
//
function registerFormCallback( name ) {
    var args = new Array( document.forms[ name ], 'onSubmit' );
    args = args.concat( toArray(arguments, 1) );
    registerCallback.apply( this, args );
}
//
// Resizes parent IFRAME to accommodate the element identified by 'id'.
//
function resizeParentFrame( id, win, offset ) {
    win = win || window;
    var frame = getParentFrame( win );
    var element = win.document.getElementById( id );
    if (! (frame && element))
        return;
    if (element.rows != null)
        frame.style.display = element.rows.length ? 'inline' : 'none';
    if (element.offsetHeight > 10) frame.height = element.offsetHeight + offset;
    if (frame.width != '100%') frame.width = element.offsetWidth + offset;
}

function displayParentFrameElement( id, win, display ) {
    win = win || window;
    var element = win.parent.document.getElementById( id );
    if( typeof(element) == 'object' ) {
      element.style.display = (display ? 'block' : 'none');
    }
}
//
// Converts array-like object to array.
//
function toArray( array_like, start, length ) {
    start = start || 0;
    var array = [], end;

    if (length == null || (end = start + length) > array_like.length)
        end = array_like.length;

    for (var i = start; i < end; i++)
        array[array.length] = array_like[i];

    return array;
}
//
// Returns windows object containing the element.
//
function getWindow( element ) {
    var doc = getDocument( element );
    return (doc.defaultView || doc.parentWindow || doc.window);
}
//
// Returns document object the element belongs to.
//
function getDocument( element ) {
    return (element.body ? element : element.ownerDocument || element.document);
}
//
// Returns an element given it's Id.
//
function getElement( element ) {
    if ( typeof element == 'string' )
        return document.getElementById( element );
    return element
}
//
// Returns parent IFRAME element of the given window object.
//
function getParentFrame( win ) {
    if (win.frameElement)
        return win.frameElement;

    var iframes = win.parent.document.getElementsByTagName( 'iframe' );
    var windows = win.parent.document.frames;
    if (windows && iframes.length != windows.length)
        return null;

    for (var i = 0; i < iframes.length; i++) {
        var iframe = iframes[i];
        if (iframe.contentWindow && iframe.contentWindow == win)
            return iframe;
        if (windows && windows[i] == win)
            return iframe;
    }

    return null;
}
