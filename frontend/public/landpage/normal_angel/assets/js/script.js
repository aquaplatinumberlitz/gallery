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
function getThemeToUse() {
    var manualTheme = localStorage.getItem('themePreference');
    var isAutoMode = localStorage.getItem('themeAutoMode') !== 'false';
    var hours = new Date().getHours();
    
    if (manualTheme && !isAutoMode) {
        return manualTheme;
    } else {
        return (hours > 5 && hours < 19) ? 'day' : 'night';
    }
}

function isAutoMode() {
    return localStorage.getItem('themeAutoMode') !== 'false';
}

/* ===== MAIN FUNCTIONALITY ===== */
$(document).ready(function() {
    var currentTheme = getThemeToUse();
    var headerBG = document.getElementById('headerBG');
    var themeToggle = document.getElementById('themeToggle');
    var themeToggleText = document.getElementById('themeToggleText');
    
    // Apply theme class
    if (currentTheme === 'night') {
        $('body').addClass('theme-night');
        if (headerBG) headerBG.className = 'night-theme';
    } else {
        $('body').addClass('theme-day');
    }
    
    // Update toggle button text
    function updateToggleText() {
        if (!themeToggleText) return;
        var theme = getThemeToUse();
        var autoIndicator = isAutoMode() ? ' (Auto)' : '';
        themeToggleText.textContent = theme === 'day' ? 'Night' + autoIndicator : 'Day' + autoIndicator;
    }
    updateToggleText();
    
    // Theme toggle click handler
    if (themeToggle) {
        $(themeToggle).on('click', function() {
            var theme = getThemeToUse();
            var newTheme = theme === 'day' ? 'night' : 'day';
            localStorage.setItem('themePreference', newTheme);
            localStorage.setItem('themeAutoMode', 'false');
            location.reload();
        });
        
        // Double click to return to auto mode
        $(themeToggle).on('dblclick', function() {
            localStorage.setItem('themeAutoMode', 'true');
            localStorage.removeItem('themePreference');
            location.reload();
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
    
    // Start animations after short delay
    setTimeout(function() {
        startAnimations();
    }, 300);
    
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
function startAnimations() {
    if ($('body').hasClass('theme-day')) {
        startDayAnimations();
    } else {
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
    $("#minidora_day").animate({top:"-=15px"}, 1000, 'easeInOutSine')
                      .animate({top:"+=15px"}, 1000, 'easeInOutSine');
    setTimeout(animateMinidora, 2000);
}

function animateDora() {
    $("#dora_day").animate({rotate:"10deg"}, 800, 'easeInOutQuad')
                  .animate({rotate:"0deg"}, 800, 'easeInOutQuad');
    setTimeout(animateDora, 1600);
}

function animateDorami() {
    $("#dorami_day").animate({rotate:"4deg"}, 120, 'easeInOutQuad')
                    .animate({rotate:"0deg"}, 120, 'easeInOutQuad');
    setTimeout(animateDorami, 240);
}

function animateClouds() {
    var cloudWidth = Math.floor($(window).width() + 600);
    
    $("#cloud1").animate({left: cloudWidth}, 65000, 'linear').animate({left: "-300px"}, 0);
    $("#cloud2").animate({left: cloudWidth}, 62000, 'linear').animate({left: "-150px"}, 0);
    $("#cloud3").animate({left: cloudWidth}, 34000, 'linear').animate({left: "-100px"}, 0);
    $("#cloud4").animate({left: cloudWidth}, 40000, 'linear').animate({left: "-150px"}, 0);
    $("#cloud5").animate({left: cloudWidth}, 58000, 'linear').animate({left: "-200px"}, 0);
    
    setTimeout(animateClouds, 1000);
}

function animateDoraAtNight() {
    $("#dora_night").animate({rotate:"15deg"}, 2000, 'easeInOutQuad')
                    .animate({rotate:"0deg"}, 2000, 'easeInOutQuad');
    setTimeout(animateDoraAtNight, 4000);
}

function animateDoramiAtNight() {
    $("#dorami_night").animate({rotate:"10deg"}, 2000, 'easeInOutQuad')
                      .animate({rotate:"0deg"}, 2000, 'easeInOutQuad');
    setTimeout(animateDoramiAtNight, 4000);
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