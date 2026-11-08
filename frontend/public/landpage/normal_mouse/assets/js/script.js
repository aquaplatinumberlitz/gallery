/*
 * jQuery Easing v1.3 - http://gsgd.co.uk/sandbox/jquery/easing/
 *
 * Uses the built in easing capabilities added In jQuery 1.1
 * to offer multiple easing options
 *
 * TERMS OF USE - jQuery Easing
 * 
 * Open source under the BSD License. 
 * 
 * Copyright © 2008 George McGinley Smith
 * All rights reserved.
 * 
 * Redistribution and use in source and binary forms, with or without modification, 
 * are permitted provided that the following conditions are met:
 * 
 * Redistributions of source code must retain the above copyright notice, this list of 
 * conditions and the following disclaimer.
 * Redistributions in binary form must reproduce the above copyright notice, this list 
 * of conditions and the following disclaimer in the documentation and/or other materials 
 * provided with the distribution.
 * 
 * Neither the name of the author nor the names of contributors may be used to endorse 
 * or promote products derived from this software without specific prior written permission.
 * 
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY 
 * EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 *  COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 *  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
 *  GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED 
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 *  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED 
 * OF THE POSSIBILITY OF SUCH DAMAGE. 
 *
*/

// t: current time, b: begInnIng value, c: change In value, d: duration
jQuery.easing['jswing'] = jQuery.easing['swing'];

jQuery.extend( jQuery.easing,
{
	def: 'easeOutQuad',
	swing: function (x, t, b, c, d) {
		//alert(jQuery.easing.default);
		return jQuery.easing[jQuery.easing.def](x, t, b, c, d);
	},
	easeInQuad: function (x, t, b, c, d) {
		return c*(t/=d)*t + b;
	},
	easeOutQuad: function (x, t, b, c, d) {
		return -c *(t/=d)*(t-2) + b;
	},
	easeInOutQuad: function (x, t, b, c, d) {
		if ((t/=d/2) < 1) return c/2*t*t + b;
		return -c/2 * ((--t)*(t-2) - 1) + b;
	},
	easeInCubic: function (x, t, b, c, d) {
		return c*(t/=d)*t*t + b;
	},
	easeOutCubic: function (x, t, b, c, d) {
		return c*((t=t/d-1)*t*t + 1) + b;
	},
	easeInOutCubic: function (x, t, b, c, d) {
		if ((t/=d/2) < 1) return c/2*t*t*t + b;
		return c/2*((t-=2)*t*t + 2) + b;
	},
	easeInQuart: function (x, t, b, c, d) {
		return c*(t/=d)*t*t*t + b;
	},
	easeOutQuart: function (x, t, b, c, d) {
		return -c * ((t=t/d-1)*t*t*t - 1) + b;
	},
	easeInOutQuart: function (x, t, b, c, d) {
		if ((t/=d/2) < 1) return c/2*t*t*t*t + b;
		return -c/2 * ((t-=2)*t*t*t - 2) + b;
	},
	easeInQuint: function (x, t, b, c, d) {
		return c*(t/=d)*t*t*t*t + b;
	},
	easeOutQuint: function (x, t, b, c, d) {
		return c*((t=t/d-1)*t*t*t*t + 1) + b;
	},
	easeInOutQuint: function (x, t, b, c, d) {
		if ((t/=d/2) < 1) return c/2*t*t*t*t*t + b;
		return c/2*((t-=2)*t*t*t*t + 2) + b;
	},
	easeInSine: function (x, t, b, c, d) {
		return -c * Math.cos(t/d * (Math.PI/2)) + c + b;
	},
	easeOutSine: function (x, t, b, c, d) {
		return c * Math.sin(t/d * (Math.PI/2)) + b;
	},
	easeInOutSine: function (x, t, b, c, d) {
		return -c/2 * (Math.cos(Math.PI*t/d) - 1) + b;
	},
	easeInExpo: function (x, t, b, c, d) {
		return (t==0) ? b : c * Math.pow(2, 10 * (t/d - 1)) + b;
	},
	easeOutExpo: function (x, t, b, c, d) {
		return (t==d) ? b+c : c * (-Math.pow(2, -10 * t/d) + 1) + b;
	},
	easeInOutExpo: function (x, t, b, c, d) {
		if (t==0) return b;
		if (t==d) return b+c;
		if ((t/=d/2) < 1) return c/2 * Math.pow(2, 10 * (t - 1)) + b;
		return c/2 * (-Math.pow(2, -10 * --t) + 2) + b;
	},
	easeInCirc: function (x, t, b, c, d) {
		return -c * (Math.sqrt(1 - (t/=d)*t) - 1) + b;
	},
	easeOutCirc: function (x, t, b, c, d) {
		return c * Math.sqrt(1 - (t=t/d-1)*t) + b;
	},
	easeInOutCirc: function (x, t, b, c, d) {
		if ((t/=d/2) < 1) return -c/2 * (Math.sqrt(1 - t*t) - 1) + b;
		return c/2 * (Math.sqrt(1 - (t-=2)*t) + 1) + b;
	},
	easeInElastic: function (x, t, b, c, d) {
		var s=1.70158;var p=0;var a=c;
		if (t==0) return b;  if ((t/=d)==1) return b+c;  if (!p) p=d*.3;
		if (a < Math.abs(c)) { a=c; var s=p/4; }
		else var s = p/(2*Math.PI) * Math.asin (c/a);
		return -(a*Math.pow(2,10*(t-=1)) * Math.sin ( (t*d-s)*(2*Math.PI)/p )) + b;
	},
	easeOutElastic: function (x, t, b, c, d) {
		var s=1.70158;var p=0;var a=c;
		if (t==0) return b;  if ((t/=d)==1) return b+c;  if (!p) p=d*.3;
		if (a < Math.abs(c)) { a=c; var s=p/4; }
		else var s = p/(2*Math.PI) * Math.asin (c/a);
		return a*Math.pow(2,-10*t) * Math.sin ( (t*d-s)*(2*Math.PI)/p ) + c + b;
	},
	easeInOutElastic: function (x, t, b, c, d) {
		var s=1.70158;var p=0;var a=c;
		if (t==0) return b;  if ((t/=d/2)==2) return b+c;  if (!p) p=d*(.3*1.5);
		if (a < Math.abs(c)) { a=c; var s=p/4; }
		else var s = p/(2*Math.PI) * Math.asin (c/a);
		if (t < 1) return -.5*(a*Math.pow(2,10*(t-=1)) * Math.sin ( (t*d-s)*(2*Math.PI)/p )) + b;
		return a*Math.pow(2,-10*(t-=1)) * Math.sin ( (t*d-s)*(2*Math.PI)/p )*.5 + c + b;
	},
	easeInBack: function (x, t, b, c, d, s) {
		if (s == undefined) s = 1.70158;
		return c*(t/=d)*t*((s+1)*t - s) + b;
	},
	easeOutBack: function (x, t, b, c, d, s) {
		if (s == undefined) s = 1.70158;
		return c*((t=t/d-1)*t*((s+1)*t + s) + 1) + b;
	},
	easeInOutBack: function (x, t, b, c, d, s) {
		if (s == undefined) s = 1.70158; 
		if ((t/=d/2) < 1) return c/2*(t*t*(((s*=(1.525))+1)*t - s)) + b;
		return c/2*((t-=2)*t*(((s*=(1.525))+1)*t + s) + 2) + b;
	},
	easeInBounce: function (x, t, b, c, d) {
		return c - jQuery.easing.easeOutBounce (x, d-t, 0, c, d) + b;
	},
	easeOutBounce: function (x, t, b, c, d) {
		if ((t/=d) < (1/2.75)) {
			return c*(7.5625*t*t) + b;
		} else if (t < (2/2.75)) {
			return c*(7.5625*(t-=(1.5/2.75))*t + .75) + b;
		} else if (t < (2.5/2.75)) {
			return c*(7.5625*(t-=(2.25/2.75))*t + .9375) + b;
		} else {
			return c*(7.5625*(t-=(2.625/2.75))*t + .984375) + b;
		}
	},
	easeInOutBounce: function (x, t, b, c, d) {
		if (t < d/2) return jQuery.easing.easeInBounce (x, t*2, 0, c, d) * .5 + b;
		return jQuery.easing.easeOutBounce (x, t*2-d, 0, c, d) * .5 + c*.5 + b;
	}
});

/*
 *
 * TERMS OF USE - EASING EQUATIONS
 * 
 * Open source under the BSD License. 
 * 
 * Copyright © 2001 Robert Penner
 * All rights reserved.
 * 
 * Redistribution and use in source and binary forms, with or without modification, 
 * are permitted provided that the following conditions are met:
 * 
 * Redistributions of source code must retain the above copyright notice, this list of 
 * conditions and the following disclaimer.
 * Redistributions in binary form must reproduce the above copyright notice, this list 
 * of conditions and the following disclaimer in the documentation and/or other materials 
 * provided with the distribution.
 * 
 * Neither the name of the author nor the names of contributors may be used to endorse 
 * or promote products derived from this software without specific prior written permission.
 * 
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY 
 * EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 *  COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 *  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
 *  GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED 
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 *  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED 
 * OF THE POSSIBILITY OF SUCH DAMAGE. 
 *
 */

(function ($) {
    // Monkey patch jQuery 1.3.1+ css() method to support CSS 'transform'
    // property uniformly across Safari/Chrome/Webkit, Firefox 3.5+, IE 9+, and Opera 11+.
    // 2009-2011 Zachary Johnson www.zachstronaut.com
    // Updated 2011.05.04 (May the fourth be with you!)
    function getTransformProperty(element)
    {
        // Try transform first for forward compatibility
        // In some versions of IE9, it is critical for msTransform to be in
        // this list before MozTranform.
        var properties = ['transform', 'WebkitTransform', 'msTransform', 'MozTransform', 'OTransform'];
        var p;
        while (p = properties.shift())
        {
            if (typeof element.style[p] != 'undefined')
            {
                return p;
            }
        }
        
        // Default to transform also
        return 'transform';
    }
    
    var _propsObj = null;
    
    var proxied = $.fn.css;
    $.fn.css = function (arg, val)
    {
        // Temporary solution for current 1.6.x incompatibility, while
        // preserving 1.3.x compatibility, until I can rewrite using CSS Hooks
        if (_propsObj === null)
        {
            if (typeof $.cssProps != 'undefined')
            {
                _propsObj = $.cssProps;
            }
            else if (typeof $.props != 'undefined')
            {
                _propsObj = $.props;
            }
            else
            {
                _propsObj = {}
            }
        }
        
        // Find the correct browser specific property and setup the mapping using
        // $.props which is used internally by jQuery.attr() when setting CSS
        // properties via either the css(name, value) or css(properties) method.
        // The problem with doing this once outside of css() method is that you
        // need a DOM node to find the right CSS property, and there is some risk
        // that somebody would call the css() method before body has loaded or any
        // DOM-is-ready events have fired.
        if
        (
            typeof _propsObj['transform'] == 'undefined'
            &&
            (
                arg == 'transform'
                ||
                (
                    typeof arg == 'object'
                    && typeof arg['transform'] != 'undefined'
                )
            )
        )
        {
            _propsObj['transform'] = getTransformProperty(this.get(0));
        }
        
        // We force the property mapping here because jQuery.attr() does
        // property mapping with jQuery.props when setting a CSS property,
        // but curCSS() does *not* do property mapping when *getting* a
        // CSS property.  (It probably should since it manually does it
        // for 'float' now anyway... but that'd require more testing.)
        //
        // But, only do the forced mapping if the correct CSS property
        // is not 'transform' and is something else.
        if (_propsObj['transform'] != 'transform')
        {
            // Call in form of css('transform' ...)
            if (arg == 'transform')
            {
                arg = _propsObj['transform'];
                
                // User wants to GET the transform CSS, and in jQuery 1.4.3
                // calls to css() for transforms return a matrix rather than
                // the actual string specified by the user... avoid that
                // behavior and return the string by calling jQuery.style()
                // directly
                if (typeof val == 'undefined' && jQuery.style)
                {
                    return jQuery.style(this.get(0), arg);
                }
            }

            // Call in form of css({'transform': ...})
            else if
            (
                typeof arg == 'object'
                && typeof arg['transform'] != 'undefined'
            )
            {
                arg[_propsObj['transform']] = arg['transform'];
                delete arg['transform'];
            }
        }
        
        return proxied.apply(this, arguments);
    };
})(jQuery);

/*!
/**
 * Monkey patch jQuery 1.3.1+ to add support for setting or animating CSS
 * scale and rotation independently.
 * https://github.com/zachstronaut/jquery-animate-css-rotate-scale
 * Released under dual MIT/GPL license just like jQuery.
 * 2009-2012 Zachary Johnson www.zachstronaut.com
 */
(function ($) {
    // Updated 2010.11.06
    // Updated 2012.10.13 - Firefox 16 transform style returns a matrix rather than a string of transform functions.  This broke the features of this jQuery patch in Firefox 16.  It should be possible to parse the matrix for both scale and rotate (especially when scale is the same for both the X and Y axis), however the matrix does have disadvantages such as using its own units and also 45deg being indistinguishable from 45+360deg.  To get around these issues, this patch tracks internally the scale, rotation, and rotation units for any elements that are .scale()'ed, .rotate()'ed, or animated.  The major consequences of this are that 1. the scaled/rotated element will blow away any other transform rules applied to the same element (such as skew or translate), and 2. the scaled/rotated element is unaware of any preset scale or rotation initally set by page CSS rules.  You will have to explicitly set the starting scale/rotation value.
    
    function initData($el) {
        var _ARS_data = $el.data('_ARS_data');
        if (!_ARS_data) {
            _ARS_data = {
                rotateUnits: 'deg',
                scale: 1,
                rotate: 0
            };
            
            $el.data('_ARS_data', _ARS_data);
        }
        
        return _ARS_data;
    }
    
    function setTransform($el, data) {
        $el.css('transform', 'rotate(' + data.rotate + data.rotateUnits + ') scale(' + data.scale + ',' + data.scale + ')');
    }
    
    $.fn.rotate = function (val) {
        var $self = $(this), m, data = initData($self);
                        
        if (typeof val == 'undefined') {
            return data.rotate + data.rotateUnits;
        }
        
        m = val.toString().match(/^(-?\d+(\.\d+)?)(.+)?$/);
        if (m) {
            if (m[3]) {
                data.rotateUnits = m[3];
            }
            
            data.rotate = m[1];
            
            setTransform($self, data);
        }
        
        return this;
    };
    
    // Note that scale is unitless.
    $.fn.scale = function (val) {
        var $self = $(this), data = initData($self);
        
        if (typeof val == 'undefined') {
            return data.scale;
        }
        
        data.scale = val;
        
        setTransform($self, data);
        
        return this;
    };

    // fx.cur() must be monkey patched because otherwise it would always
    // return 0 for current rotate and scale values
    var curProxied = $.fx.prototype.cur;
    $.fx.prototype.cur = function () {
        if (this.prop == 'rotate') {
            return parseFloat($(this.elem).rotate());
            
        } else if (this.prop == 'scale') {
            return parseFloat($(this.elem).scale());
        }
        
        return curProxied.apply(this, arguments);
    };
    
    $.fx.step.rotate = function (fx) {
        var data = initData($(fx.elem));
        $(fx.elem).rotate(fx.now + data.rotateUnits);
    };
    
    $.fx.step.scale = function (fx) {
        $(fx.elem).scale(fx.now);
    };
    
    /*
    
    Starting on line 3905 of jquery-1.3.2.js we have this code:
    
    // We need to compute starting value
    if ( unit != "px" ) {
        self.style[ name ] = (end || 1) + unit;
        start = ((end || 1) / e.cur(true)) * start;
        self.style[ name ] = start + unit;
    }
    
    This creates a problem where we cannot give units to our custom animation
    because if we do then this code will execute and because self.style[name]
    does not exist where name is our custom animation's name then e.cur(true)
    will likely return zero and create a divide by zero bug which will set
    start to NaN.
    
    The following monkey patch for animate() gets around this by storing the
    units used in the rotation definition and then stripping the units off.
    
    */
    
    var animateProxied = $.fn.animate;
    $.fn.animate = function (prop) {
        if (typeof prop['rotate'] != 'undefined') {
            var $self, data, m = prop['rotate'].toString().match(/^(([+-]=)?(-?\d+(\.\d+)?))(.+)?$/);
            if (m && m[5]) {
                $self = $(this);
                data = initData($self);
                data.rotateUnits = m[5];
            }
            
            prop['rotate'] = m[1];
        }
        
        return animateProxied.apply(this, arguments);
    };
})(jQuery);

//////////////////////////////////
//ページ内リンクでアニメーション//
//////////////////////////////////

$(function(){
$('a[href^=#]').click(function(){
var speed = 500;
var href= $(this).attr("href");
var target = $(href == "#" || href == "" ? 'html' : href);
var position = target.offset().top;
$("html, body").animate({scrollTop:position}, speed, "swing");
return false;
});
});


//////////////////////////////
//マウスオーバーで画像が光る//
//////////////////////////////

$(function(){
$("a img").hover(
function(){
$(this).fadeTo(200, 0.5);
},
function(){
$(this).fadeTo(100, 1.0);
}
);
});

$(function(){
$("a div").hover(
function(){
$(this).fadeTo(200, 0.5);
},
function(){
$(this).fadeTo(100, 1.0);
}
);
});



/////////////////////////
//スクロールでgoTop出現//
/////////////////////////

$(function() {
var topBtn = $('#goTop');
topBtn.hide();
//スクロールが100に達したらボタン表示
$(window).scroll(function () {
if ($(this).scrollTop() > 100) {
topBtn.fadeIn();
} else {
topBtn.fadeOut();
}
});
//スクロールしてトップ
topBtn.click(function () {
$('body,html').animate({
scrollTop: 0
}, 500);
return false;
    });
});


////////////////////////////////////
//ポップアップwindow（サイズ固定）//
////////////////////////////////////

function openWin(url,winName,w){
screenH = screen.height*0.7;
new_win = window.open(url,winName,'toolbar=no,status=no,directories=no,scrollbars=yes,location=no,resizable=yes,menubar=no,status=no,toolbar=no,width='+w+',height='+screenH);
new_win.focus();
}



///////////////////////////
//flashムービーのストップ//
///////////////////////////

function movieStop(){
if(navigator.userAgent.indexOf("Win") != -1){
var element = document.getElementById("newtop");
if(element && typeof element.jtoa === "function") {
    element.jtoa("false");
}
}
else{
var element = document.getElementById("noIEnewtop");
if(element && typeof element.jtoa === "function") {
    element.jtoa("false");
}
}
}
function movieStart(){
if(navigator.userAgent.indexOf("Win") != -1){
var element = document.getElementById("newtop");
if(element && typeof element.jtoa === "function") {
    element.jtoa("true");
}
}
else{
var element = document.getElementById("noIEnewtop");
if(element && typeof element.jtoa === "function") {
    element.jtoa("true");
}
}
}

/////////////////////
//TOPアニメーション//
/////////////////////

// Theme management functions
// localStorage can throw when storage is blocked (sandboxed iframe, privacy mode)
function storageGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
}

function storageSet(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
}

function storageRemove(key) {
    try { localStorage.removeItem(key); } catch (e) {}
}

function timeBasedTheme() {
    var hours = new Date().getHours();
    return (hours > 5 && hours < 19) ? 'day' : 'night';
}

function getThemeToUse() {
    var manualTheme = storageGet('themePreference');
    var isAutoMode = storageGet('themeAutoMode') !== 'false';

    if ((manualTheme === 'day' || manualTheme === 'night') && !isAutoMode) {
        return manualTheme;
    }
    return timeBasedTheme();
}

function isAutoMode() {
    return storageGet('themeAutoMode') !== 'false';
}

/* ===== SCENES (day / night) =====
 * Only the active scene's images are requested: scene images carry `data-src` and get their `src` when the scene
 * is first shown. The header backgrounds are CSS, so they load with the theme class. Switching scenes happens in
 * place (no page reload): swap classes, stop the old scene's jQuery loops, start the new scene's. */
var DAY_ELEMENTS = '#minidora_day, #dora_day, #dorami_day, #cloud1, #cloud2, #cloud3, #cloud4, #cloud5';
var NIGHT_ELEMENTS = '#dora_night, #dorami_night';
var activeScene = null;      // scene currently on screen (null before the first paint)
var switchToken = 0;         // invalidates a pending scene swap when the user clicks again

// Header backgrounds are CSS-owned; these URLs are only used to warm the cache before a swap.
var SCENE_BACKGROUNDS = {
    day: 'assets/img/top_headbg_day.gif',
    night: 'assets/img/top_headbg_night.webp'
};

var warmedBackgrounds = {};

// Start fetching a scene's images and call `done` once they are all decoded (or failed). Safe to call repeatedly.
function loadScene(theme, done) {
    var pending = 1;
    function settle() { if (--pending === 0 && done) done(); }
    $('[data-scene="' + theme + '"] img[data-src]').each(function() {
        var img = this;
        img.setAttribute('src', img.getAttribute('data-src'));
        img.removeAttribute('data-src');
    });
    $('[data-scene="' + theme + '"] img').each(function() {
        var img = this;
        if (img.complete) return;
        pending++;
        $(img).one('load error', settle);
    });
    if (!warmedBackgrounds[theme]) {
        warmedBackgrounds[theme] = true;
        pending++;
        var bg = new Image();
        bg.onload = bg.onerror = settle;
        bg.src = SCENE_BACKGROUNDS[theme];
    }
    settle();
}

// Remove every animated inline style so a scene starts from its stylesheet position again.
function resetAnimated($els) {
    $els.each(function() {
        this.style.top = '';
        this.style.left = '';
        this.style.transform = '';
        $(this).removeData('_ARS_data');
    });
}

function stopAnimations() {
    var $els = $(DAY_ELEMENTS + ', ' + NIGHT_ELEMENTS);
    $els.stop(true);
    resetAnimated($els);
}

function applyScene(theme) {
    var headerBG = document.getElementById('headerBG');
    stopAnimations();
    activeScene = theme;
    $('body').removeClass('theme-day theme-night').addClass('theme-' + theme);
    if (headerBG) headerBG.className = theme === 'night' ? 'night-theme' : '';
    startAnimations();
}

/* ===== MAIN FUNCTIONALITY ===== */
$(document).ready(function() {
    var themeToggle = document.getElementById('themeToggle');
    var themeToggleText = document.getElementById('themeToggleText');
    var themeAuto = document.getElementById('themeAuto');
    var shownTheme = getThemeToUse();
    var intended = shownTheme;   // last requested theme, even while its swap is pending
    var autoMode = isAutoMode(); // kept in memory too, so the toggle still works when storage is blocked

    // First paint: show the chosen scene as soon as its own images are requested.
    loadScene(shownTheme);
    applyScene(shownTheme);

    // The button names the theme a click switches to; "Auto" appears only while a manual choice is active.
    function updateToggle(theme) {
        if (themeToggleText) {
            var autoIndicator = autoMode ? ' (Auto)' : '';
            themeToggleText.textContent = theme === 'day' ? 'Night' + autoIndicator : 'Day' + autoIndicator;
        }
        if (themeToggle) $(themeToggle).toggleClass('is-manual', !autoMode);
    }
    updateToggle(shownTheme);

    // Switch scenes in place. The label updates at once; the scene swaps as soon as its images are ready
    // (immediately when they are already loaded).
    function switchTo(theme) {
        var token = ++switchToken;
        updateToggle(theme);
        var swapped = false;
        function swap() {
            if (swapped || token !== switchToken) return;
            swapped = true;
            shownTheme = theme;
            applyScene(theme);
        }
        if (theme === activeScene) return;
        loadScene(theme, swap);
        setTimeout(swap, 1500); // never leave the old scene up if an image stalls
    }

    if (themeToggle) {
        // Warm the other scene while the pointer is on its way to the button.
        $(themeToggle).on('pointerenter pointerdown focusin', function() {
            loadScene(shownTheme === 'day' ? 'night' : 'day');
        });

        $(themeToggle).on('click', function(e) {
            if ($(e.target).closest('#themeAuto').length) return;
            var newTheme = intended === 'day' ? 'night' : 'day';
            intended = newTheme;
            autoMode = false;
            storageSet('themePreference', newTheme);
            storageSet('themeAutoMode', 'false');
            switchTo(newTheme);
        });

        $(themeToggle).on('keydown', function(e) {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            e.preventDefault();
            (e.target === themeAuto ? $(themeAuto) : $(themeToggle)).trigger('click');
        });
    }

    // Back to automatic (time-based) mode, without delaying a normal click.
    if (themeAuto) {
        $(themeAuto).on('click', function(e) {
            e.stopPropagation();
            storageSet('themeAutoMode', 'true');
            storageRemove('themePreference');
            autoMode = true;
            intended = timeBasedTheme();
            switchTo(intended);
        });
    }

    // Initialize Nivo Slider
    $(window).on('load', function() {
        $('#slider').nivoSlider({
            effect:'boxRainGrowReverse',
            animSpeed:500,
            pauseTime:5000,
            directionNav: false,
            controlNav: true,
            pauseOnHover: true
        });
    });
});

/* ===== ANIMATION FUNCTIONS ===== */
// Each loop re-arms itself from its completion callback. `.stop(true)` clears the queue so a stopped loop never
// re-arms; the `activeScene` guard also covers a callback that was already running when the scene changed.
function startAnimations() {
    if (activeScene === 'day') {
        animation();
    } else if (activeScene === 'night') {
        animation_night();
    }
}

function animation(){
dora_day();
minidora_day();
dorami_day();
cloud1();
cloud2();
cloud3();
cloud4();
cloud5();
}

function minidora_day(){
    if (activeScene !== 'day') return;
    $("#minidora_day").animate({top:"-=15px"}, 1000, 'easeInOutSine').animate({top:"+=15px"}, 1000, 'easeInOutSine', minidora_day);
}

function dora_day(){
    if (activeScene !== 'day') return;
    $("#dora_day").animate({top:"-=90px"}, 250, 'easeOutQuad').animate({top:"+=90px"}, 250, 'easeInQuad', dora_day);
}

function dorami_day(){
    if (activeScene !== 'day') return;
    $("#dorami_day").animate({rotate:"4deg"}, 120, 'easeInOutQuad').animate({rotate:"0deg"}, 120, 'easeInOutQuad', dorami_day);
}

var cloudWidth = Math.floor($(window).width() + 600);

function cloud1(){
    if (activeScene !== 'day') return;
    $("#cloud1").animate({left: cloudWidth}, 65000, 'linear').animate({left: "-300px"}, 0, cloud1);
}

function cloud2(){
    if (activeScene !== 'day') return;
    $("#cloud2").animate({left: cloudWidth}, 62000, 'linear').animate({left: "-150px"}, 0, cloud2);
}

function cloud3(){
    if (activeScene !== 'day') return;
    $("#cloud3").animate({left: cloudWidth}, 34000, 'linear').animate({left: "-100px"}, 0, cloud3);
}

function cloud4(){
    if (activeScene !== 'day') return;
    $("#cloud4").animate({left: cloudWidth}, 40000, 'linear').animate({left: "-150px"}, 0, cloud4);
}

function cloud5(){
    if (activeScene !== 'day') return;
    $("#cloud5").animate({left: cloudWidth}, 58000, 'linear').animate({left: "-200px"}, 0, cloud5);
}

/////////////////////
//TOPアニメーション(夜)//
/////////////////////

function animation_night(){
dora_night();
dorami_night();
}

function dora_night(){
    if (activeScene !== 'night') return;
    $("#dora_night").animate({rotate:"15deg"}, 2000, 'easeInOutQuad').animate({rotate:"0deg"}, 2000, 'easeInOutQuad', dora_night);
}

function dorami_night(){
    if (activeScene !== 'night') return;
    $("#dorami_night").animate({rotate:"10deg"}, 2000, 'easeInOutQuad').animate({rotate:"0deg"}, 2000, 'easeInOutQuad', dorami_night);
}
