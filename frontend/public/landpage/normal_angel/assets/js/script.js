/*!
 * Landing Page Script - Doraemon Website
 * Combined essential JavaScript functionality
 */

/* ===== EASING FUNCTIONS ===== */
jQuery.easing['jswing'] = jQuery.easing['swing'];

jQuery.extend( jQuery.easing, {
	def: 'easeOutQuad',
	swing: function (x, t, b, c, d) {
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
	easeInSine: function (x, t, b, c, d) {
		return -c * Math.cos(t/d * (Math.PI/2)) + c + b;
	},
	easeOutSine: function (x, t, b, c, d) {
		return c * Math.sin(t/d * (Math.PI/2)) + b;
	},
	easeInOutSine: function (x, t, b, c, d) {
		return -c/2 * (Math.cos(Math.PI*t/d) - 1) + b;
	}
});

/* ===== CSS TRANSFORM SUPPORT ===== */
(function ($) {
    function getTransformProperty(element) {
        var properties = ['transform', 'WebkitTransform', 'msTransform', 'MozTransform', 'OTransform'];
        var p;
        while (p = properties.shift()) {
            if (typeof element.style[p] != 'undefined') {
                return p;
            }
        }
        return 'transform';
    }
    
    var _propsObj = null;
    var proxied = $.fn.css;
    $.fn.css = function (arg, val) {
        if (_propsObj === null) {
            if (typeof $.cssProps != 'undefined') {
                _propsObj = $.cssProps;
            } else if (typeof $.props != 'undefined') {
                _propsObj = $.props;
            } else {
                _propsObj = {}
            }
        }
        
        if (typeof _propsObj['transform'] == 'undefined' && (arg == 'transform' || (typeof arg == 'object' && typeof arg['transform'] != 'undefined'))) {
            _propsObj['transform'] = getTransformProperty(this.get(0));
        }
        
        if (_propsObj['transform'] != 'transform') {
            if (arg == 'transform') {
                arg = _propsObj['transform'];
                if (typeof val == 'undefined' && jQuery.style) {
                    return jQuery.style(this.get(0), arg);
                }
            } else if (typeof arg == 'object' && typeof arg['transform'] != 'undefined') {
                arg[_propsObj['transform']] = arg['transform'];
                delete arg['transform'];
            }
        }
        
        return proxied.apply(this, arguments);
    };
})(jQuery);

/* ===== ROTATE AND SCALE ANIMATION ===== */
(function ($) {
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
    
    $.fn.scale = function (val) {
        var $self = $(this), data = initData($self);
        
        if (typeof val == 'undefined') {
            return data.scale;
        }
        
        data.scale = val;
        setTransform($self, data);
        return this;
    };

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

/* ===== THEME MANAGEMENT ===== */
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

    // Smooth scroll for anchor links
    $('a[href^=#]').click(function(){
        var speed = 500;
        var href= $(this).attr("href");
        var target = $(href == "#" || href == "" ? 'html' : href);
        if(target.length > 0) {
            var position = target.offset().top;
            $("html, body").animate({scrollTop:position}, speed, "swing");
        }
        return false;
    });

    // Image hover effects
    $("a img").hover(
        function(){
            $(this).fadeTo(200, 0.5);
        },
        function(){
            $(this).fadeTo(100, 1.0);
        }
    );

    // Back to Top functionality
    initBackToTop();
});

/* ===== ANIMATION FUNCTIONS ===== */
// Each loop re-arms itself from its completion callback. `.stop(true)` clears the queue so a stopped loop never
// re-arms; the `activeScene` guard also covers a callback that was already running when the scene changed.
function startAnimations() {
    if (activeScene === 'day') {
        startDayAnimations();
    } else if (activeScene === 'night') {
        startNightAnimations();
    }
}

function startDayAnimations() {
    animateMinidora();
    animateDora();
    animateDorami();
    animateClouds();
}

function startNightAnimations() {
    animateDoraAtNight();
    animateDoramiAtNight();
}

function animateMinidora() {
    if (activeScene !== 'day') return;
    $("#minidora_day").animate({top:"-=15px"}, 1000, 'easeInOutSine')
                      .animate({top:"+=15px"}, 1000, 'easeInOutSine', animateMinidora);
}

function animateDora() {
    if (activeScene !== 'day') return;
    $("#dora_day").animate({rotate:"10deg"}, 800, 'easeInOutQuad')
                  .animate({rotate:"0deg"}, 800, 'easeInOutQuad', animateDora);
}

function animateDorami() {
    if (activeScene !== 'day') return;
    $("#dorami_day").animate({rotate:"4deg"}, 120, 'easeInOutQuad')
                    .animate({rotate:"0deg"}, 120, 'easeInOutQuad', animateDorami);
}

function animateClouds() {
    animateCloud("#cloud1", 65000, "-300px");
    animateCloud("#cloud2", 62000, "-150px");
    animateCloud("#cloud3", 34000, "-100px");
    animateCloud("#cloud4", 40000, "-150px");
    animateCloud("#cloud5", 58000, "-200px");
}

function animateCloud(selector, duration, resetLeft) {
    if (activeScene !== 'day') return;
    var cloudWidth = Math.floor($(window).width() + 600);
    $(selector).animate({left: cloudWidth}, duration, 'linear').animate({left: resetLeft}, 0, function() {
        animateCloud(selector, duration, resetLeft);
    });
}

function animateDoraAtNight() {
    if (activeScene !== 'night') return;
    $("#dora_night").animate({rotate:"15deg"}, 2000, 'easeInOutQuad')
                    .animate({rotate:"0deg"}, 2000, 'easeInOutQuad', animateDoraAtNight);
}

function animateDoramiAtNight() {
    if (activeScene !== 'night') return;
    $("#dorami_night").animate({rotate:"10deg"}, 2000, 'easeInOutQuad')
                      .animate({rotate:"0deg"}, 2000, 'easeInOutQuad', animateDoramiAtNight);
}

/* ===== BACK TO TOP FUNCTIONALITY ===== */
function initBackToTop() {
    var $backToTop = $('#backToTop');
    var $window = $(window);
    
    $window.scroll(function() {
        if ($window.scrollTop() > 300) {
            $backToTop.addClass('show');
        } else {
            $backToTop.removeClass('show');
        }
    });
    
    $backToTop.click(function(e) {
        e.preventDefault();
        $('html, body').animate({
            scrollTop: 0
        }, 800, 'easeOutQuad');
        return false;
    });
}