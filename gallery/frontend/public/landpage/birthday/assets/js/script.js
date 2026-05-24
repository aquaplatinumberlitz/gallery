// ============================================
// ESSENTIAL FUNCTIONALITY FOR DORAEMON LANDING PAGE
// ============================================

// Essential jQuery Easing Functions
jQuery.easing['jswing'] = jQuery.easing['swing'];
jQuery.extend( jQuery.easing, {
	def: 'easeOutQuad',
	swing: function (x, t, b, c, d) {
		return -c *(t/=d)*(t-2) + b; // Use easeOutQuad directly
	},
	easeOutQuad: function (x, t, b, c, d) {
		return -c *(t/=d)*(t-2) + b;
	},
	easeInOutQuad: function (x, t, b, c, d) {
		if ((t/=d/2) < 1) return c/2*t*t + b;
		return -c/2 * ((--t)*(t-2) - 1) + b;
	},
	easeInOutSine: function (x, t, b, c, d) {
		return -c/2 * (Math.cos(Math.PI*t/d) - 1) + b;
	}
});

$(document).ready(function() {
    
    // ============================================
    // PAGE ANIMATIONS
    // ============================================
    
    // Smooth scrolling for anchor links
    $('a[href^=#]').click(function(){
        var speed = 500;
        var href= $(this).attr("href");
        var target = $(href == "#" || href == "" ? 'html' : href);
        if(target.length) {
            var position = target.offset().top;
            $("html, body").animate({scrollTop:position}, speed, "swing");
            return false;
        }
    });

    // Hover effects for images and divs
    $("a img").hover(
        function(){
            $(this).fadeTo(200, 0.5);
        },
        function(){
            $(this).fadeTo(100, 1.0);
        }
    );

    $("a div").hover(
        function(){
            $(this).fadeTo(200, 0.5);
        },
        function(){
            $(this).fadeTo(100, 1.0);
        }
    );

    // ============================================
    // BIRTHDAY ANIMATIONS
    // ============================================
    
    function birth14dora(){
        $("#birth14dora").animateRotate(7, 400, 'easeInOutQuad')
                         .animateRotate(0, 400, 'easeInOutQuad');
        setTimeout(birth14dora, 800);
    }

    function birth14baloon(){
        var time = 1500;
        var easingName = 'easeInOutQuad';
        $("#birth14baloon").animate({marginTop:"-10px"}, time, easingName)
                          .animate({marginTop:"0"}, time, easingName);
        setTimeout(birth14baloon, time*2);
    }

    // Start birthday animations after page load
    setTimeout(function() {
        birth14dora();
        birth14baloon();
    }, 1000);

    // ============================================
    // NIVO SLIDER FUNCTIONALITY
    // ============================================
    
    $(window).load(function() {
        if($.fn.nivoSlider) {
            $('#slider').nivoSlider({
                effect:'boxRainGrowReverse',
                animSpeed:500,
                pauseTime:5000,
                directionNav: false,
                controlNav: true,
                pauseOnHover: true
            });
        }
    });

    // ============================================
    // MOBILE DETECTION AND REDIRECTION
    // ============================================
    
    var ua = navigator.userAgent;
    if(ua.indexOf('iPhone') > 0 || ua.indexOf('iPod') > 0 || 
       (ua.indexOf('Android') > 0 && ua.indexOf('Mobile') > 0) || 
       (ua.indexOf('Android') > 0 && ua.indexOf('Opera Mini') > 0) || 
       (ua.indexOf('Android') > 0 && ua.indexOf('Opera Mobile') > 0)) {
        // Mobile detected - for a landing page, we'll just add a mobile class
        $('body').addClass('mobile-device');
    }

    // ============================================
    // CONTENT RANDOMIZATION (SIMPLIFIED)
    // ============================================
    
    // Simplified slide content array
    var slideContent = [
        '<a href="#"><img src="assets/img/m0.jpg" alt="Slide 1"/></a>',
        '<a href="#"><img src="assets/img/m1.jpg" alt="Slide 2"/></a>',
        '<a href="#"><img src="assets/img/m2.jpg" alt="Slide 3"/></a>',
        '<a href="#"><img src="assets/img/m3.jpg" alt="Slide 4"/></a>',
        '<a href="#"><img src="assets/img/m4.jpg" alt="Slide 5"/></a>',
        '<a href="#"><img src="assets/img/m5.jpg" alt="Slide 6"/></a>'
    ];

    // Initialize slider content if slider exists
    if($('#slider').length) {
        var sliderHtml = '';
        for(var i = 0; i < slideContent.length; i++) {
            sliderHtml += slideContent[i] + '\n';
        }
        $('#slider').html(sliderHtml);
    }

    // ============================================
    // UTILITY FUNCTIONS
    // ============================================
    
    // Function to handle popup windows (disabled for landing page)
    window.openWin = function(url, winName, w) {
        // Disabled for landing page - just return false
        return false;
    };

    // Movie control functions (disabled for landing page)
    window.movieStop = function() {
        // Disabled for landing page
    };
    
    window.movieStart = function() {
        // Disabled for landing page
    };
});

// ============================================
// CSS TRANSFORM AND ROTATION SUPPORT
// ============================================

// Basic CSS transform support for animations
(function($) {
    $.fn.rotate = function(degrees) {
        $(this).css({
            '-webkit-transform': 'rotate(' + degrees + 'deg)',
            '-moz-transform': 'rotate(' + degrees + 'deg)',
            '-ms-transform': 'rotate(' + degrees + 'deg)',
            '-o-transform': 'rotate(' + degrees + 'deg)',
            'transform': 'rotate(' + degrees + 'deg)'
        });
        return $(this);
    };
    
    // Animation extension for rotation with proper callback
    $.fn.animateRotate = function(angle, duration, easing, complete) {
        var $this = $(this);
        var currentRotation = 0;
        
        return $this.animate({ rotateAngle: angle }, {
            duration: duration || 400,
            easing: easing || 'swing',
            step: function(now) {
                $this.css({
                    '-webkit-transform': 'rotate(' + now + 'deg)',
                    '-moz-transform': 'rotate(' + now + 'deg)',
                    '-ms-transform': 'rotate(' + now + 'deg)',
                    '-o-transform': 'rotate(' + now + 'deg)',
                    'transform': 'rotate(' + now + 'deg)'
                });
            },
            complete: complete || function(){}
        });
    };
})(jQuery);