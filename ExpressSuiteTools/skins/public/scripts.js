//
// $Id: scripts.js,v 1.1.2.1.6.5.4.11 2005/02/22 10:04:21 $
//
// *** Checked 26/03/2009 ***

//
// MS IE 5.0 does not support Function.apply and .call methods,
// thus we have this hack.
//
if( Function.prototype.apply == null ) {
    Function.prototype.apply = function (o, a) {
        o.__f = this;

        var params = [];
        for (var i = 0; i < a.length; i++)
            params[i] = 'a[' + i + ']';

        try {
            return eval( 'o.__f(' + params.join(',') + ')' );
        }
        finally {
            var error;
            try { delete o.__f; }
            catch (error) { o.__f = null; }
        }
    }
}

if( Function.prototype.call == null ) {
    Function.prototype.call = function( func )
    {
        return this.apply( func, toArray(arguments, 1) );
    };
}
//
// Detect user agent type, version and features
//
function BrowserType() {
    //var s = '';
    //for (k in navigator)
    //	s += k+'="'+navigator[k]+'"\n';
    //alert(s);
    var version = navigator.appVersion;
    var error;

    if( navigator.appName == 'Microsoft Internet Explorer' ) {
        this.type = 'IE';
        this.version = parseFloat( version.substr( version.indexOf('MSIE') + 4 ) );
        this.hasCoveredBug = true;
        this.brokenSetMultiple = true;

        var xmlhttp_classes = ['msxml2.XMLHTTP.4.0', 'Microsoft.XMLHTTP'];
        for( var i = 0; i < xmlhttp_classes.length; i++ )
            try {
                new ActiveXObject(xmlhttp_classes[i]);
                this.hasXMLHTTP = true;
                // XXX: actually decoding bug was fixed between msxml 3.0 SP1 and SP3,
                //      but we cannot detect that some service pack was installed
                this.hasDecodingBug = (i != 0);
                break;
            } catch (error) {
                // pass
            }
    } else if( navigator.product == 'Gecko' ) {
        this.type = 'MZ';
        this[ 'NS6' ] = true;
        try {
            new XMLHttpRequest();
            this.hasXMLHTTP = true;
        } catch (error) {
            // pass
        }
    } else if( navigator.appName == 'Netscape' ) {
        this.type = 'NS';
        if (navigator.vendor == 'Netscape6')
            this.version = 6;
    }

    if( ! this.version )
        this.version = parseFloat(version);

    this.major = parseInt( this.version );

    if( this.type ) {
        this[ this.type ] = true;
        this[ this.type + this.major ] = true;
        this[ this.type + this.version ] = true;
    }

    this.hasComputedStyle = !! (window.document.defaultView &&
        window.document.defaultView.getComputedStyle);
}
//
// Creates custom exception object
//
function Exception( name, message, kw ) {
    var exception = {};

    exception.name = name;
    exception.message = message;
    exception.toString = function () { return message };

    if( kw != null )
        for( var k in kw ) exception[k] = kw[k];

    return exception;
}

BrowserType.prototype.downloadURL = function(url, ready_callback, error_callback) {
    var async = (ready_callback != null),
        hasDecodingBug = this.hasDecodingBug,
        request;

    if( async && error_callback == null ) error_callback = function() {};

    if( ! this.hasXMLHTTP ) {
        var error = Exception('NotImplemented', "XMLHTTP is not supported by your browser");

        if( async ) {
            error_callback(error);
            return;
        } else
            throw error;
    }

    if( this.IE ) // IE MSXML object
        request = new ActiveXObject('Microsoft.XMLHTTP');
    else // Mozilla object
        request = new XMLHttpRequest();

    function processResponse()
    {
        if( async && request.readyState != 4 ) return;
        var responseText = '';

        if( ! hasDecodingBug )
            responseText = request.responseText;
        else {
            // workaround of msxml charset decoding bug (code was taken from
            // http://relib.com/forums/topic.asp?id=751103)
            var rs = new ActiveXObject('ADODB.Recordset');

            rs.Fields.Append('ru', 200, 100000);
            rs.Open();
            rs.AddNew();
            rs(0).AppendChunk(request.ResponseBody);
            responseText += rs(0);
            rs.Close();
        }

        if( request.status == 200 ) {
            if (async) ready_callback(responseText);
            else return responseText;
        } else {
            var error = Exception( 'DownloadError'
                                 , request.status + ' ' + request.statusText
                                 , {'status': request.status, 'text': responseText}
                                 );
            if( async ) error_callback(error);
                  else throw error;
        }
    }

    if( async ) request.onreadystatechange = processResponse;

    if( this.IE ) // XXX
        url = setParam(url, '_T', (new Date().getTime()));

    request.open('GET', url, async);
    request.send(null);

    if(! async) return processResponse();
};
//
// Get actual width of the given frame object
//
BrowserType.prototype.frameWidth = function( frame )
{
    if( this.IE ) {

	if( this.version < 5.5 )
	    return frame.document.body.offsetWidth;

	// TODO: use frame index
	else if( this.version < 6 )
	    return parseInt( frame.parent.document.body.cols ) &&
		   frame.document.body.offsetWidth;
	else
	    return parseInt( frame.parent.document.body.cols );
    }

    return frame.innerWidth;
}
//
// Set query parameter in the url string
//
function setParam( url, name, value ) {
    var url_hash = url.split('#'),
        url = url_hash[0],
        hash = (url_hash[1] ? '#' + url_hash[1] : '');

    name = escapeURL(name);
    value = name + '=' + escapeURL(value);

    if (url.indexOf('?') == -1)
        return url + '?' + value + hash;

    var param_re = new RegExp( '([?&])' + name + '=[^&]*' );
    if (url.match( param_re ))
        // replace existing value
        return url.replace( param_re, '\$1' + value ) + hash;

    return url + '&' + value + hash;
}
//
// Escape special characters in the HTML string
//
function escapeHTML( str, nlbr ) {
    for( var c in escapeHTMLMap )
        str = str.replace( new RegExp(c, 'g'), escapeHTMLMap[c] );
    if( nlbr )
    	str = str.replace( new RegExp('\r*\n', 'g'), '<br />\n' );
    return str;
}
//
// Escape special characters in the URL string
//
function escapeURL( str ) {
    var plusRegexp = new RegExp('\\+', 'g');

    if( ! userAgent.IE )
        return escape(str).replace(plusRegexp, '%2B');

    else {
        // convert cyrillic characters from unicode into cp1251 and escape it
        // (native IE method escapes unicode in proprietary format %u1234)
        var r = '';
        str += ''; // convert str to string

        for( var i = 0; i < str.length; i++ ) {
            var n = str.charCodeAt(i);

            if( n >= 0x410 && n <= 0x44F ) // À-ÿ
                n -= 0x350;
            else if( n == 0x451 ) // ¸
                n = 0xB8;
            else if( n == 0x401 ) // ¨
                n = 0xA8;

            if( (n != 42 && n < 45) || (57 < n && n < 65) || (90 < n && n != 95 && n < 97) || (122 < n && n < 256) )
                r += '%' + (n < 16 ? '0' : '') + n.toString(16);
            else
                r += str.charAt(i);
        }

        return r;
    }
}

function getEventTarget( ev ) {
    ev = ev || window.event;
    var ob = ev.target || ev.srcElement;
    if( ob.tagName.toLowerCase() == 'option' || ob.tagName.toLowerCase() == 'span' )
        ob = ob.parentNode;
    return ob;
}

function getElement( element ) {
    if( typeof (element) == 'string' )
        return document.getElementById( element );
    return element
}

function displayElements( show, hide ) {
    if( hide ) {
        for( i = 0; i < hide.length; i++ ) {
            getElement( hide[ i ] ).style.display = 'none';
        }
    }
    if( show ) {
        for( i = 0; i < show.length; i++ ) {
            var element = getElement( show[ i ] );
            element.style.display = '';
            if( userAgent.MZ ) {
                // workaround of Mozilla bug
                var selects = element.getElementsByTagName('SELECT');
                for( var j = selects.length; j-- > 0; )
                    selects[j].style.visibility = 'visible';
            }
        }
    }
}
//
// Make frameset
//
function makeFrameset( menu ) {
    document.open();
    menu_width = getCookie( 'FramesetWidth' );
    default_menu_width = 270;
    if( !menu_width || menu_width < 270 || menu_width > 600 ) menu_width = default_menu_width;
    if( self.screen && ':270:320:350:380:420'.indexOf( menu_width.toString() ) > 0 ) { 
        if( screen.width > 1400 ) menu_width = 420; else
        //if( screen.width > 1280 ) menu_width = 380; else
        //if( screen.width > 1152 ) menu_width = 350; else
        //if( screen.width > 1024 ) menu_width = 320; else
        menu_width = default_menu_width;
	}
    document.write(
    '<frameset cols="' + menu_width + ',*" framespacing="1">\n' +
    ( menu ? '<frame name="menu" src="" scrolling="no" marginwidth="0" marginheight="0" frameborder="0">\n' : '' ) +
    '<frame name="workspace" scrolling="no" marginwidth="0" marginheight="0" frameborder="0">\n' +
	'</frameset>\n'
    );
    var frame = getMenuFrame();
    if( frame ) frame.savedWidth = menu_width;
    document.close();
}
//
// Check for top level frameset and create it if necessary
//
function checkFrameSet() {
    if( ! window.openInFrame ) return true;

    url = window.redirectURL || window.location.href;

    if( window.parent.frames.length > 0 ) {
        if( window.openInFrame == 'workspace' && window.name == 'workfield' ) {
	    	// workspace was incorrectly opened in the workfield
            window.parent.location.replace( url );
            return false;
        }
        if( window.openInFrame == 'workfield' && window.name == 'workspace' ) {
	    	// workfield was incorrectly opened as the workspace
		    window.location.replace( objectBaseURL + '/inFrame?link=' + escapeURL(url) );
            return false;
        }
		// frames seem to be ok
		return true;
    }

    makeFrameset( 1 );

    if( userAgent.IE ) { url = setParam( url, '_R', Math.random() ); }

    if( window.openInFrame == 'workfield' ) {
        url = objectBaseURL + '/inFrame?link=' + escapeURL( url );
	}

    if( expand_workplace && !checkExpanded() ) {
        toggleExpand( 1 );
        window.frames.menu.IsExpandFramespace = true;
    } else {
        window.frames.menu.location.replace( getMenuFrameURL() );
    }

    window.frames.workspace.location.replace( url );
    return false;
}
//
//	Check and return menu frame
//
function getMenuFrame() {
    try {
        return top.frames['menu'];
    } catch (error) {
        return null;
    }
}
//
//	Return menu frame URL
//
function getMenuFrameURL() {
    return portalRootURL + '/menu';
}
//
//	Check expanded workspace
//
function checkExpanded() {
    var isExpanded = false;
    if( ! window.parent ) return isExpanded;

    var frame = getMenuFrame();
    if( ! frame ) return 1;

    var width = userAgent.frameWidth( frame );
    if( frame.savedWidth && width <= 1 ) isExpanded = true;
	return isExpanded;
}
//
// Toggle expanded workspace view
//
function toggleExpand( save_frameset_width ) {
    if( ! window.parent ) return;

    var frame = getMenuFrame();
    if( ! frame ) return;

    var width = userAgent.frameWidth( frame );

    IsSaveFramesetWidth = ( save_frameset_width == '1' ? true : false );
    IsExpandFramespace = frame.IsExpandFramespace;

    if( IsExpandFramespace ) {
        frame.location.replace( getMenuFrameURL() );
        frame.IsExpandFramespace = false;
        frame.needsUpdate = 'main';
    }

    if( IsExpandFramespace || frame.savedWidth && width <= 1 ) {
        top.document.body.cols = frame.savedWidth + ',*';
        frame.savedWidth = null;

        if( frame.needsUpdate != null )
            updateNavFrame();
    } else {
        top.document.body.cols = '0,*';
        frame.savedWidth = width;
        if( IsSaveFramesetWidth ) setCookie( 'FramesetWidth', width );
    }
}
//
// Refresh navigation frame
//
function updateNavFrame( section ) {
    if( ! window.parent ) return;

    var frame = getMenuFrame();
    if( ! frame ) return;

    var width = userAgent.frameWidth( frame );

    if( section == null && frame.needsUpdate != null ) {
		section = frame.needsUpdate;
		frame.needsUpdate = null;
    }
	if( section == 'main' ) {
	 	try { frame.reload( 'navMembers', 0 ); } catch (error) {}
		return;
	}

    if( frame.savedWidth && width <= 1 ) {
		// navigation frame is hidden
		frame.needsUpdate = section;
		return;
    }
    // do actual refresh
    try { frame.reload( section, 1 ); } catch (error) {}
}
//
// Open user info popup
//
function OpenUserInfoWnd( user, params ) {
    var url = setParam( window.objectBaseURL + '/user_info_form', 'userid', user );
    if( ! params ) {
       params = 'toolbar=no,scrollbars=no,status=yes,top=40,left=100,width=450,height=520,resizable=no';
    }
    window.open( url, '_blank', params );
}

function OpenGroupInfoWnd( group, params ) {
    var url = setParam( window.objectBaseURL + '/group_info_form', 'groupid', group );
    if( ! params ) {
       params = 'toolbar=no,scrollbars=yes,status=no,top=240,left=60,width=460,height=210,resizable=no';
    }
    window.open( url, '_blank', params );
}

function OpenUserActivityWnd( params ) {
    var url = window.objectBaseURL + '/activity_statistics_form';
    if( ! params ) {
       params = 'toolbar=no,scrollbars=no,status=yes,top=40,left=100,width=490,height=620,resizable=no';
    }
    window.open( url, '_blank', params );
}

function OpenRegistryWnd( mode, num ){
    var url = window.objectBaseURL + '/registry_ids_list';
    //'<dtml-var "this().getVersion().absolute_url()">'
    H = (typeof(num) == 'number' ? 40 * num : 0);
    window.open( url, 'wnd_popup_menu', 'toolbar=no,scrollbars=no,width=380,height='+(120+H)+',resizable=yes' );
}

function OpenGroupsListWnd( attr, params, callback ) {
    var url = window.objectBaseURL + '/groups_list_form';

    url = setParam( url, 'callback', callback );
	url = setParam( url, 'attr', attr );

    if( ! params ) {
       params = 'toolbar=yes,scrollbars=yes,status=yes,width=620,height=620,resizable=yes';
    }
    window.open( url, '_blank', params );
}

//
// Open site object selection box
// callback_function will be called with 2 params: uid, title
//
function OpenDocumentSelectionWnd( callback_form, callback_function, search_path, search_types, uid_field, title_field ) {
    var url = window.objectBaseURL + '/document_link_form';

    url = setParam( url, 'callback_function', callback_function );
    url = setParam( url, 'callback_form', callback_form );
    url = setParam( url, 'uid_field', uid_field );
    url = setParam( url, 'title_field', title_field );

    if( search_path && search_path != '' )
        url = setParam( url, 'search_path', search_path );
    if( search_types && search_path != '' )
        url = setParam( url, 'search_types', search_types );

    width = ( self.screen ? Math.min(screen.width - 200, 800) : 650 );
    window.open( url, '_blank', 'toolbar=no,scrollbars=yes,status=yes,top=100,left=100,width='+width+',height=450,resizable=yes' );
}

function OpenFolderSelectionWnd( uid_field, title_field ) {
    var url = window.objectBaseURL + '/wizard_folders';

    url = setParam( url, 'uid_field', uid_field );
    url = setParam( url, 'title_field', title_field );

    window.open( url, '_blank', 'toolbar=no,scrollbars=yes,top=100,left=100,width=320,height=500,resizable=yes' );
}

function OpenCategorySelectionWnd( uid_field, title_field, category ) {
    var url = window.objectBaseURL + '/wizard_category_objects';

    url = setParam( url, 'uid_field', uid_field );
    url = setParam( url, 'title_field', title_field );
	url = setParam( url, 'category', category );

    window.open( url, '_blank', 'toolbar=no,scrollbars=yes,top=100,left=100,width=640,height=500,resizable=yes' );
}

function open_folders_wnd() {
    var url = window.objectBaseURL + '/wizard_folders';
    window.open( url, 'wnd_popup_menu', 'toolbar=no,scrollbars=yes,top=100,left=100,width=320,height=500,resizable=yes' );
}

function OpenAttributeSelectionWnd( callback_form, callback_function, attr_field, value_field, mode ) {
    var url = window.objectBaseURL + '/attribute_selection_form';

    url = setParam( url, 'callback_function', callback_function );
    url = setParam( url, 'callback_form', callback_form );
    url = setParam( url, 'attr_field', attr_field );
    url = setParam( url, 'value_field', value_field );
    /*
    if( !mode || mode == 'invoke' )
      var status = 'toolbar=no,scrollbars=yes,status=no,top=100,left=200,width=620,height=510,resizable=yes';
    else
      var status = 'toolbar=no,scrollbars=yes,status=no,top=195,left=200,width=620,height=380,resizable=yes';
    */
    var status = 'toolbar=no,scrollbars=yes,status=no,top=100,left=60,width=740,height=380,resizable=yes';
    window.open( url, '_blank', status );
}
//
// this function returns to callback_function: title, path_to_object
//
function OpenDocumentSelectionWndPath(  callback_function,nwidth,nheight ) {
    var url = setParam( window.objectBaseURL + '/document_link_form', 'callback_function', callback_function );
    url = setParam( url, 'callback_form', 'yes' ); // needed
    url = setParam( url, 'getPath', '1');
    var sSize=',width='+( nwidth > 0 ? nwidth : 450 )+',height='+( nheight > 0 ? nheight : 550 );
    window.open( url, '_blank', 'toolbar=no,scrollbars=yes,status=yes,resizable=yes'+sSize );
}
//
// Preload rollover images
//
function preloadImages() {
    var images = preloadImages.arguments;
    var preload = preloadArray;

    if( typeof(images) == 'object' )
	images = images[0];

    for( var i in images ) {
	  var image = preload[ preload.length ] = new Image();
	  image.src = portalImagesURL + '/' + images[i];
    }
}
//
// Roll the image on event
//
function change( image, what ) {
    var name;
    switch (what) {
       case 1: name= image.name + '_over.gif'; break;
       case 2: name= image.name + '.gif'; break;
       case 3: name= image.name + '_click.gif'; break;
       case 4: name= image.name + '_down.gif'; break;
    }

    if( name ) image.src = portalImagesURL + '/' + name;
}
//
// Hide/show overlapped elements on the page.
// Adapted from JSCalendar by Mihai Bazon, <mishoo@infoiasi.ro>
//
function hideCoveredElements( element, hide ) {
    if( hide == null ) hide = true;

    var doc = element.ownerDocument || element.document;
    var tags = [ 'applet', 'iframe', 'select' ];
    var p = getAbsolutePos(element);
    var x1 = p.x1;
    var x2 = p.x2;
    var y1 = p.y1;
    var y2 = p.y2;

    for( var i = tags.length; i-- > 0; ) {
        var objs = doc.getElementsByTagName(tags[i]);

        for( j = objs.length; j-- > 0; ) {
            var obj = objs[j];
            var v;

            if( hide ) {
                v = getStyleProp(obj, 'visibility');
                if( v == 'hidden' ) continue;
                p = getAbsolutePos(obj);
                if (p.x1 > x2 || p.x2 < x1 || p.y1 > y2 || p.y2 < y1) continue;
                obj._app_saved_visibility = v;
                obj.style.visibility = 'hidden';
            } else if( obj._app_saved_visibility ) {
                obj.style.visibility = obj._app_saved_visibility;
                obj._app_saved_visibility = null;
            }
        }
    }
}
//
// Returns record of element's dimensions and position in a window.
//
function getAbsolutePos( element ) {
    var pos = { x1: element.offsetLeft, y1: element.offsetTop };
    if( element.offsetParent ) {
        var par = getAbsolutePos(element.offsetParent);
        pos.x1 += par.x1;
        pos.y1 += par.y1;
    }
    pos.x2 = pos.x1 + ( pos.w = element.offsetWidth  ) - 1;
    pos.y2 = pos.y1 + ( pos.h = element.offsetHeight ) - 1;
    return pos;
}
//
// Returns current value of the elements's style property.
//
function getStyleProp( element, style ) {
    var value = element.style[ style ];
    if( value )
    	return value;

    if( userAgent.hasComputedStyle ) {
        var doc = element.ownerDocument || element.document;
        value = doc.defaultView.getComputedStyle(element, '').getPropertyValue(style);
    } else if( element.currentStyle ) {
        value = element.currentStyle[ style ];
    }
    return value;
}
//
// Returns event's target element.
//
function getEventTarget( ev ) {
    ev = ev || window.event;
    var ob = ev.target || ev.srcElement;
    if( ob.tagName.toLowerCase() == 'option' || ob.tagName.toLowerCase() == 'span' )
        ob = ob.parentNode;
    return ob;
}
//
// Determines whether the element is the original event target.
//
function isElementEventTarget( ev, element ) {
    ev = ev || window.event;

    var target = ev.explicitOriginalTarget;
    if( target != null ) {
        if( target.tagName.toLowerCase() == 'span' ) target = target.parentNode;
        return (target == element);
    }

    var x = ev.clientX;
    var y = ev.clientY;
    var p = getAbsolutePos(element);

    return (x >= p.x1 && x <= p.x2 && y >= p.y1 && y <= p.y2);
}
//
// Update comment resolution field.
//
function onChangeResolutionItem( event, editor, notes ) {
    var list = getEventTarget(event);
    if( typeof(list) != 'object' || list.selectedIndex == 0 ) return;
	
    var name = list.name.substr(0, list.name.length-5) + editor;
    var target = document.all[ name ];
    if( typeof(target) != 'object' ) return;

    var id = list.options[ list.selectedIndex ].id;
    var value = commentTexts[ list.name ][ list.selectedIndex ] ||
        list.options[ list.selectedIndex ].text;

    if( editor ) {
        var text = target.innerHTML;
        var re = /[\n]+/g;
        value = value.replace( re, '<br>' );
        if( text.indexOf(value) == -1 ) {
            value = '<p class=commission id="'+id+'"><font color=blue>' + value + '</font></p><p>' + notes + '</p>';
            target.innerHTML += value;
        }
    } else if( target.type == 'textarea' ) {
        var re = new RegExp( '[ \t]+$' );
        var text = target.value.replace( re, '' );
        if( text.indexOf(value) == -1 ) {
            if( text.length && text.substr(text.length-1) != '\n' ) value = '\n\n' + value;
            target.value += value;
        }
    } else {
	    target.value = value;
    }

    target.typedString = '';
    target.focus();
}

function CheckAndRefreshCommentFields( frm, fields ) {
    var re = /[\f\r\t\v\n]+/g;
    for( var i = 0; i < fields.length; i++ ) {
      try { 
        var name = fields[i];
        var text = document.all[name+'_editor'].innerHTML;
        text = HTMLCleanup( text, 0, 0, 0, 1 );
        text = text.replace( re, '' );
        if( text ) frm[name].value = '<div class=comments>' + text + '</div>';
      } catch (error) { continue; }
    }
}
//
// Returns corresponding label element for the form input field.
//
function getLabelFor( form, elem ) {
    var name;
    if( typeof(elem) == 'object' )
        name = elem.name.toLowerCase();
    else
        name = elem.toString().toLowerCase();

    var labels = form.getElementsByTagName('label');

    for( var i = 0; i < labels.length; i++ ) {
        var htmlfor = labels[i].htmlFor;
        if( htmlfor && htmlfor.toLowerCase() == name ) return labels[i];
    }
    return null;
}
//
// Navigates the browser to the URL of the first child link element.
//
function followInnerLink( element ) {
    var links = element.getElementsByTagName('a');
    if( links ) {
        // TODO handle target frame
        window.location.href = links[0].href;
        return false;
    }
    return true;
}
//
// Validate user form (used in heading/manage_access_form, membership/change_ownership_form)
//
function validateUserForm(form) {
    if( !testField( form.userid, null, messageCatalog.select_user ) )
        return false;
    if( form['roles:list'] && !testField( form['roles:list'], null, messageCatalog.select_role ) )
        return false;
    return true;
}
//
// Validate range
//
function validateRange( type, min, max ) {
    var rx_min = validationRegexp[type].exec(min),
        rx_max = validationRegexp[type].exec(max),
        from, till;

    switch (type) {
        case 'datetime':
            from = new Date(rx_min[3],rx_min[2],rx_min[1],rx_min[5],rx_min[6]);
            till = new Date(rx_max[3],rx_max[2],rx_max[1],rx_max[5],rx_max[6]);
            break;

        default:
            from = rx_min[0];
            till = rx_max[0];
    }
    return (from <= till);
}
//
// Validate date
//
function validateDate( year, month, day ) {
    month = month - 1
    var tempDate = new Date(year, month, day)
    return ( (tempDate.getFullYear() == year) &&
             (tempDate.getMonth() == month) &&
             (tempDate.getDate() == day) )
}
//
// Validate time
//
function validateTime( hour, minute ) {
    return ( Number(hour) < 24 && Number(minute) < 60 )
}
//
// Validate object identifier
//
function validateIdentifier( field, message, allowEmpty ) {
    return testField( field, identifierRegexp, message, allowEmpty );
}
//
// Validate object identifier (strong version)
//
function validateIdentifierStrong( field, message ) {
    return testField( field, identifierStrongRegexp, message, false );
}

var custom_empty_date = '__';

function check_empty_date( frm, name ) {
    var error;
    if( !name ) return;
	try {
      var value = frm.elements[name].value;
      frm.elements[name+'_button'].disabled = (value.substr(0,2) == custom_empty_date ? true : false);
    }
    catch( error ) {
      //pass
    }
}

function check_unique_subject( s1, s2 ) {
    var reg_spec = /[\.\,\;\-\=\\\/\*\+\(\)\&\^\%\$\#\@\!\_\?]/g;
    var reg_comma = /[«»"' \s\d]/g;

    s1 = s1.replace(reg_spec, '').replace(reg_comma, '').toLowerCase();
    s2 = s2.replace(reg_spec, '').replace(reg_comma, '').toLowerCase();
    if( s1==s2 || s1.indexOf(s2) > -1 ) return true;

    return false;
}
//
// Validate field value by type, using associated regular expression.
//
function testField( field, type, message, allow_empty ) {
    var value = field.value;
    var regexp;

    if( typeof(type) == 'string' ) {
        if (type.substr(type.length-1) == '_')
            type = type.substr(0, type.length-1);
        regexp = validationRegexp[ type ];
    } else if( type != null ) {
        regexp = type;
        type = null;
    }

    if( ! message )
        message = field.getAttribute('validation_message');

    if( type == 'required' )
        allow_empty = false;

    else if( allow_empty == null )
        allow_empty = ! message;

    if( ! message ) {
        message = validationMessages[ type ];
        if (! message)
            return true;
    }

    if( type == 'date' && value.substr(0,2) == custom_empty_date ) return true;	

    do {
        if( emptyValueRegexp.test( value ) ) {
            if( value.length )
                // prevent whitespace from being submitted
                field.value = '';
            if( ! allow_empty ) break;
            // value is not required?
            return true;
        }

        if (regexp && ! regexp.test(value)) break;

        if( type == 'id' || type == 'idstrong' ) {
            if( value.substr( 0,1 ) == '_' ) break;
            if( value.substr( 0,3 ) == 'aq_' ) break;
            if( value.substr(-2,2 ) == '__' ) break;
        }
        else if( type == 'date' ) {
            if( ! validateDate(RegExp.$3, RegExp.$2, RegExp.$1) ) break;
        }
        else if( type == 'datetime' ) {
            if( ! validateDate(RegExp.$3, RegExp.$2, RegExp.$1)) break;
            if( RegExp.$4 && ! validateTime(RegExp.$5, RegExp.$6)) break;
        }
        else if( type == 'search' ) {
            if( value.split('(').length != value.split(')').length ) break; // may be this check in RegExp???
        }

        // value is ok
        return true;
    } while (false);

    field.focus();
    if( field.select != null )
        field.select();

    alert( messageCatalog[ message ] || message );
    return false;
}
//
// Validate form by detecting special fields
//
function validateForm( form, allow_empty ) {
    var elements = form.elements;

    for( var i = 0; i < elements.length; i++ ) {
        var element = elements[i];
        with (element)
            if (! ( (type == 'text' || type == 'textarea' || type == 'select-one') &&
                     name && fieldFormatRegexp.test(name) ))
                continue;
        if (! testField(element, RegExp.$1, null, allow_empty))
            return false;
    }

    return true;
}
//
//  Sets focus to the first visible element of form
//
function focusForm( form ) {
    var element;
    for( var i=0; i<form.elements.length; i++ ) {
        element = form.elements[i];
        if (element.type != 'hidden') {
            element.focus();
            break;
        }
    }
}
//
//  Selects users in textarea - quick search
//
function SearchStrInSelect( str, select ) {
    var strn=0, strl=0;
    for( var i = 0; i < select.length; i++ ) {
        select.options[i].selected = false;
        var curl = 0;
        var inpStr = str.toUpperCase();
        var selStr = select.options[i].text.toUpperCase();
        for( var l = 0; l < str.length+1; l++ ) {
            curl = l;
            if( inpStr.charAt(l) != selStr.charAt(l) ) break;
        }
        if( curl > strl ) { strl=curl; strn=i; }
    }
    if( ! select.multiple || str.length ) select.options[strn].selected = true;
}
//
// Adds a new option to the list
//
function addOptionTo( list, text, value ) {
    var len = list.length;
    var opt;

    if( userAgent.IE )
        opt = list.document.createElement("OPTION");
    else
        opt = new Option();

    opt = list.options[len] = opt;
    opt.text = text;
    opt.value = value;
    return opt;
}
//
// Add the selected items from the source to destination list
//
function addSelectionToList( src_list, dest_list, type_of_list ) {
    var len = dest_list.length;
    var prefix = ( type_of_list ? type_of_list+':' : '' );

    for( var i = 0; i < src_list.length; i++ ) {
        if( src_list.options[i] != null && src_list.options[i].selected ) {
            //Check if this value already exist in the dest_list or not
            //if not then add it otherwise do not add it.
            var found = false;

            for( var count = 0; count < len; count++ ) {
                if( dest_list.options[count] != null ) {
                    var value = dest_list.options[count].value;
                    value = value.replace(prefix+'');
                    if( src_list.options[i].value == value ) {
                        found = true;
                        break;
                    }
                }
            }

            if( found != true ) {
                addOptionTo(dest_list, src_list.options[i].text, prefix+src_list.options[i].value);
                len++;
            }
        }
    }
}
//
// Deletes from the destination list
//
function deleteSelectionFromList( dest_list )	{
    var len = dest_list.options.length;
    for( var i = (len-1); i >= 0; i-- ) {
        if( dest_list.options[i] != null && dest_list.options[i].selected == true ) {
            dest_list.options[i] = null;
        }
    }
}
//
// Clear list contents
//
function clearList( list ) {
    var len = list.options.length;
    for( var j = (len-1); j >= 0; j-- ) {
       if( list.options[j] != null ) { list.options[j] = null; }
    }
}
//
// Fill up user's list contents from template
//
function fillupUserList( list, all_users, all_groups, template ) {
    var inv_usr_len = 0;
    var all_users = ( typeof(all_users)=='object' ? all_users : null );
    var all_groups = ( typeof(all_groups)=='object' ? all_groups : null );
    for( var t_usr=0; t_usr < template.length; t_usr++ ) {
        var value = template[t_usr];
        var IsGroup = ( value.substr(0,5)=='group' ? 1 : 0 );
        if( IsGroup && all_groups ) {
            value = value.substr(6);
            var obj = all_groups;
        } else {
            var obj = all_users;
        }
        for( var usr=0; usr < obj.options.length; usr++ ) {
            if( value==obj.options[usr].value ) {
                //create new option
                list.options[inv_usr_len] = new Option(value);
                list.options[inv_usr_len].text = obj.options[usr].text;
                list.options[inv_usr_len].value = template[t_usr];
                inv_usr_len++;
                break;
            }
        }
    }
}
//
// Returns the checked option of the radio buttons set
//
function getCheckedRadioButton( radio ) {
	len = ( typeof(radio) == 'object' ? radio.length : 0 );
    if( len )
        for ( i = 0; i < len; i++ ) {
            option = radio[i];
            if (option.checked)
                return option;
        }
    else
        return radio;
}
//
// Select all items of the list
//
function selectAll( list ) {
	var len = list.length;
	for( var i = 0; i < len; i++ ) {
		list.options[i].selected = true;
	}
}
//
// Returns document object the element belongs to.
//
function getDocument( element ) {
    return (element.body ? element : element.ownerDocument || element.document);
}
//
// Copies all options from one select control to another.
//
function copySelectOptions( source, target, state ) {
    var tdoc = getDocument( target );
    var topts = target.options;

    while (topts.length)
        topts[0] = null;

    for( var i = 0; i < source.options.length; i++ ) {
        var so = source.options[i];
        var to = tdoc.createElement('option');

        to.text = so.text;
        to.value = so.value;

        topts[ topts.length ] = to;
        if (state) to.selected = so.selected;
    }
}
//
// Copies value of one input field to another.
//
function copyFieldValue( source, target ) {
    if( source.type != target.type )
        return;

    switch (source.type) {
        case 'checkbox':
        case 'radio':
            target.value = source.value;
            target.checked = source.checked;
            break;
        case 'select-one':
        case 'select-multiple':
            copySelectOptions( source, target, true );
            break;
        default:
            target.value = source.value;
    }
}
//
// Copies input fields from source to target form.
//
// Arguments:
//
//     'source' -- source form object
//     'target' -- target form object
//
function copyFormItems( source, target ) {
    var tdoc = getDocument( target );
    var create = false;

    for( var i = 0; i < source.elements.length; i++ ) {
        var se = source.elements[ i ];
        var te = target.elements[ se.name ];

        if( te == null ) {
            var tag = se.tagName;
            if( userAgent.brokenSetMultiple && se.type == 'select-multiple' )
                tag = '<select multiple>';

            te = tdoc.createElement( tag );
            te.name = se.name;

            if( te.multiple != se.multiple )
                te.multiple  = se.multiple;
            if( te.type != se.type )
                te.type  = se.type;

            te.style.display = 'none';
            target.appendChild( te );
        }

        copyFieldValue( se, te );
    }
}
//
// Enable/disable control
//
function setControlState( form, element_id, state ) {
    if( typeof(form[element_id]) == 'object' ) form[element_id].disabled = !state;
}
//
// Opens an URL in a workspace window
//
function openUrl( url, target ) {
    if( ! url )
    	return;
    parent[target].location.href = url;
}
//
// Tests whether the given character is alphanumeric.
//
function isAlnum( ch ) {
    return wordCharRegexp.test(ch) || ch.charCodeAt(0) > 127;
}
//
// Checking the search string specially for incoming documents number
//
function checkSearchString( obj ) {
    if( typeof(obj) == 'object' ) {
      var str = obj.value;
      str = str.replace(/[\/]/g, ' ');
      str = str.replace(/[\?]/g, '');
      obj.value = str;
    }
}
//
// Open users metadata edit form div 
//
function openUsers( id ) {
    var obj = document.all[id];
    if( typeof(obj) != 'object' ) return;
    var s = (obj.style.display == 'none' ? 'block' : 'none');
	obj.style.display = s;
}
//
// Cookies
//
function getCookie( name ) {
    var prefix = name + '=';
    var s = document.cookie;
    var start = s.indexOf(prefix);
    if( start == -1 ) return null;
    var end = s.indexOf(';', start + prefix.length);
    if( end == -1 ) end = s.length;
    var value = s.substring(start + prefix.length, end);
    return unescape(value);
}

function setCookie( name, value ) {
    var expires = new Date(2030,1,20);
    var path = '/';
    var newCookie = name + '=' + escape(value) + ';expires=' + expires.toGMTString() + ';path=' + path;
    document.cookie = newCookie;
}

function path() {
	var loc = new String(document.location.href); 
	var m = 0;
    for( i=0; i<loc.length; i++ ) {
        if( loc.charAt(i) == "/" ) {
            n2=i+1;
            if( m == 2 ) n1=i;
            m++;
        }
    }
    loc = loc.substring(n1,n2);
    return loc;
}
//
// Menu pointers
//
function MM_preloadImages() {
  var d=document; if(d.images){ if(!d.MM_p) d.MM_p=new Array();
    var i,j=d.MM_p.length,a=MM_preloadImages.arguments; for(i=0; i<a.length; i++)
    if (a[i].indexOf("#")!=0){ d.MM_p[j]=new Image; d.MM_p[j++].src=a[i];}}
}

function MM_swapImgRestore() {
  var i,x,a=document.MM_sr; for(i=0;a&&i<a.length&&(x=a[i])&&x.oSrc;i++) x.src=x.oSrc;
}

function MM_findObj( n, d ) {
  var p,i,x;  if(!d) d=document; if((p=n.indexOf("?"))>0&&parent.frames.length) {
    d=parent.frames[n.substring(p+1)].document; n=n.substring(0,p);}
  if(!(x=d[n])&&d.all) x=d.all[n]; for (i=0;!x&&i<d.forms.length;i++) x=d.forms[i][n];
  for(i=0;!x&&d.layers&&i<d.layers.length;i++) x=MM_findObj(n,d.layers[i].document); return x;
}

function MM_swapImage() {
  var i,j=0,x,a=MM_swapImage.arguments; document.MM_sr=new Array; for(i=0;i<(a.length-2);i+=3)
   if ((x=MM_findObj(a[i]))!=null){document.MM_sr[j++]=x; if(!x.oSrc) x.oSrc=x.src; x.src=a[i+2];}
}

function pointer( obj, mouse, color_over, color_out ) {
    color = (mouse == 'over' ? color_over : color_out);
    obj.bgColor = color;
}

function point( idCell, color ) {
	eval('document.all.'+idCell+'.style.background = "'+color+'"');
	eval('document.getElementById("' + idCell + '").style.background = "'+color+'"');
}

///////////////////////////////////////////////////////////////////////////

var escapeHTMLMap = { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' };
var wordCharRegexp = new RegExp('\\w');

var fieldFormatRegexp = new RegExp( ':(string|int|long|float|currency|required|search|date_|datetime|id|idstrong)_?\\b' );
var emptyValueRegexp = new RegExp( '^\\s*$' );

var emailRegexp = new RegExp( '^[_a-z0-9\-\.]+@[_a-z0-9\-\.]+\.[_a-z0-9]+$', 'i' );
var dateTimeRegexp = new RegExp( '^(\\d{1,2})[\-\./](\\d{1,2})[\-\./](\\d{4})(\\s+(\\d{1,2}):(\\d{1,2}))?\\s*$' );
var identifierRegexp = new RegExp( '^[_a-z0-9\-\.\$\(\)#~, ]+$', 'i' );
var identifierStrongRegexp = new RegExp( '^[_a-z0-9\-]+$', 'i' );
var intRegexp = new RegExp( '^-?\\d+$' );
var longRegexp = new RegExp( '^-?\\d+[Ll]?$' );
var floatRegexp = new RegExp( '^-?\\d+(\.\\d+)?$' );

var userAgent = new BrowserType();
var preloadArray = new Array();
var messageCatalog = new Object();
var portalImagesURL = portalRootURL;
var commentTexts = {};

var validationRegexp = {
'int'      : new RegExp( '^-?\\d+$' ),
'long'     : new RegExp( '^-?\\d+[Ll]?$' ),
'float'    : new RegExp( '^-?\\d+[.,]?\\d*$' ),
'currency' : new RegExp( '^-?\\d+[.,]?\\d{0,2}$' ),
'datetime' : new RegExp( '^(\\d{1,2})[-./](\\d{1,2})[-./](\\d{4})(\\s+(\\d{1,2}):(\\d{1,2}))?\\s*$' ),
'email'    : new RegExp( '^[a-z0-9_.-]+@[a-z0-9_.-]+\\.[a-z0-9_]+$', 'i' ),
'id'       : new RegExp( '^[a-z0-9_.$()~, -]+$', 'i' ),
'idstrong' : new RegExp( '^[a-z][a-z0-9_]*$', 'i' ),
'required' : new RegExp( '\\S' ), // this not needed now
'search'   : new RegExp( '^[\\s()]*((%[^%*?()\\s]+|\\*?[^%*?()\\s]+\\*?)($|[\\s()]+))+$' ) // TextIndexNG search pattern
};
validationRegexp['date'] = validationRegexp['datetime'];

var validationMessages = {
'string'   : 'enter_string',
'int'      : 'enter_integer',
'long'     : 'enter_long',
'float'    : 'enter_float',
'currency' : 'enter_currency',
'date'     : 'invalid_date',
'datetime' : 'invalid_date',
'email'    : 'invalid_email',
'id'       : 'invalid_id',
'idstrong' : 'invalid_id',
'required' : 'required_input',
'search'   : 'invalid_pattern'
};

var IsSaveFramesetWidth = false;

// create frameset unless it already exists
if( checkFrameSet() ) {
    // change to another location if redirect was requested
    if( window.redirectURL ) {
        window.location.replace( window.redirectURL );
	}
    // set top level window title to current page title
    if( window.name == 'workspace' && window != top ) {
        top.document.title = document.title;
	}
    // preload page common images
    if( window.commonImages ) {
        preloadImages( window.commonImages );
	}
}

// refresh navigation frame sections
if( window.updateSections ) {
    var sections = window.updateSections.split(' ');
    for( var i in sections )
        updateNavFrame( sections[i] );
}
