// Essential JavaScript for the landing page

// jQuery Easing functions (simplified)
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
	}
});

// CSS Transform support
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
        
        if (typeof _propsObj['transform'] == 'undefined' && 
            (arg == 'transform' || (typeof arg == 'object' && typeof arg['transform'] != 'undefined'))) {
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

// Rotate animation support
$.fn.rotate = function(options) {
    return this.each(function() {
        var element = $(this);
        var rotation = options;
        element.css('transform', 'rotate(' + rotation + ')');
    });
};

// Animation functions
$(document).ready(function() {
    setTimeout(animation, 300);
    
    // Image hover effects
    $("a img").hover(
        function(){
            $(this).fadeTo(200, 0.5);
        },
        function(){
            $(this).fadeTo(100, 1.0);
        }
    );
    
    // Initialize snowfall
    initSnowfall();
    
    // Initialize Nivo Slider
    $('#slider').nivoSlider({
        effect: 'boxRainGrowReverse',
        animSpeed: 500,
        pauseTime: 5000,
        directionNav: false,
        controlNav: true,
        pauseOnHover: true
    });
});

function animation(){
    balloon();
    adballoon();
    dora();
    // Cloud animations removed - no cloud images in this theme
}

function balloon(){
    $("#top_anniv_balloon").animate({top:"-=10px"}, 2000, 'easeInOutQuad').animate({top:"+=10px"}, 2000, 'easeInOutQuad');
    setTimeout(balloon, 2000);
}

function adballoon(){
    $("#top_anniv_adballoon1").animate({rotate:"3deg"}, 3000, 'easeInOutQuad').animate({rotate:"0deg"}, 3000, 'easeInOutQuad');
    $("#top_anniv_adballoon2").animate({rotate:"3deg"}, 3000, 'easeInOutQuad').animate({rotate:"0deg"}, 3000, 'easeInOutQuad');
    setTimeout(adballoon, 6000);
}

function dora(){
    $("#top_anniv_dora").animate({rotate:"10deg"}, 500, 'easeInOutQuad').animate({rotate:"0deg"}, 500, 'easeInOutQuad');
    setTimeout(dora, 1000);
}

// Cloud animation functions removed - this theme uses snowfall effect instead

// Enhanced Snowfall effect matching legacy performance
function initSnowfall() {
    var flakes = [];
    var flakeCount = 100;  // Increased to match legacy
    var flakeImages = [
        'assets/img/ticker1.png',
        'assets/img/ticker2.png',
        'assets/img/ticker3.png',
        'assets/img/ticker4.png',
        'assets/img/ticker5.png'
    ];
    
    function random(min, max) {
        return Math.round(min + Math.random()*(max-min));
    }
    
    function randArray(arr) {
        var i = arr.length;
        while (i) {
            var y = Math.floor(Math.random()*i);
            var t = arr[--i];
            arr[i] = arr[y];
            arr[y] = t;
        }
        return arr;
    }
    
    function createFlake(id) {
        var elWidth = $(window).width();
        var elHeight = $(window).height();
        var x = random(0, elWidth);
        var y = random(-100, -10);
        var size = random(11, 18);  // Match legacy size range
        var speed = random(8, 30) / 10;  // Match legacy speed range (0.8-3.0)
        var angle = random(0, 360);
        var stepSize = random(1, 10) / 100;
        var step = 0;
        var imageIndex = random(0, flakeImages.length - 1);
        
        var flake = $('<img>')
            .attr('src', flakeImages[imageIndex])
            .attr('id', 'flake-' + id)
            .css({
                'position': 'fixed',
                'top': y + 'px',
                'left': x + 'px',
                'width': size + 'px',
                'height': size + 'px',
                'z-index': 1,
                'pointer-events': 'none',
                'transform': 'rotate(' + angle + 'deg)',
                '-moz-transform': 'rotate(' + angle + 'deg)',
                '-webkit-transform': 'rotate(' + angle + 'deg)'
            });
        
        $('body').append(flake);
        
        return {
            element: flake,
            id: id,
            x: x,
            y: y,
            speed: speed,
            step: step,
            stepSize: stepSize,
            size: size,
            update: function() {
                this.y += this.speed;
                
                if (this.y > $(window).height() + 20) {
                    this.reset();
                }
                
                this.element.css({
                    'top': this.y + 'px',
                    'left': this.x + 'px'
                });
                
                this.step += this.stepSize;
                this.x += Math.cos(this.step);
                
                if (this.x > $(window).width() - 22 || this.x < 22) {
                    this.reset();
                }
            },
            reset: function() {
                this.y = 0;
                this.x = random(0, $(window).width());
                this.stepSize = random(1, 10) / 100;
                this.size = random(11, 18);
                this.speed = random(8, 30) / 10;
                this.element.css({
                    'width': this.size + 'px',
                    'height': this.size + 'px'
                });
            }
        };
    }
    
    // Create flakes
    for (var i = 0; i < flakeCount; i++) {
        flakes.push(createFlake(i));
    }
    
    // Animation loop matching legacy timing (30ms)
    function animate() {
        for (var i = 0; i < flakes.length; i++) {
            flakes[i].update();
        }
        setTimeout(animate, 30);  // Match legacy 30ms timing
    }
    
    animate();
}

// Legacy flash movie controls removed - no longer needed