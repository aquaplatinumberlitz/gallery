/* 3F Fansub Landing Page Scripts */

// jQuery Easing Functions (Essential ones only)
jQuery.easing['jswing'] = jQuery.easing['swing'];
jQuery.extend( jQuery.easing, {
	def: 'easeOutQuad',
	swing: function (x, t, b, c, d) {
		return jQuery.easing.easeOutQuad(x, t, b, c, d);
	},
	easeOutQuad: function (x, t, b, c, d) {
		return -c *(t/=d)*(t-2) + b;
	},
	easeInOutQuad: function (x, t, b, c, d) {
		if ((t/=d/2) < 1) return c/2*t*t + b;
		return -c/2 * ((--t)*(t-2) - 1) + b;
	}
});

// Page Scroll Animation
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

// Image Hover Effects
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

// Go to Top Button
$(function() {
	var topBtn = $('#goTop');
	topBtn.hide();
	
	$(window).scroll(function () {
		if ($(this).scrollTop() > 100) {
			topBtn.fadeIn();
		} else {
			topBtn.fadeOut();
		}
	});
	
	topBtn.click(function () {
		$('body,html').animate({
			scrollTop: 0
		}, 500);
		return false;
	});
});

// New Year Animation Scripts
var fps = 25;
var animationInterval;
var mochi_id = "newyear_mochidora";
var mochi_width = 176;
var mochi_height = 236;
var mochi_src = "./assets/img/newyear_mochidora.png";
var mochi_frame = 0;
var mochi_max_frame = 100;
var mochi_onceFlg = false;

var nobi_id = "newyear_nobitako";
var nobi_width = 460;
var nobi_height = 180;
var nobi_bgposition = 0;
var nobi_src = "./assets/img/newyear_nobitako.png";
var nobi_frame = 0;
var nobi_max_frame = 24;
var nobi_onceFlg = false;

$(document).ready(function() {
	setTimeout(function() {
		animation();
	}, 300);
	
	// Initialize Nivo Slider
	$(window).on('load', function() {
		$('#slider').nivoSlider({
			effect: 'boxRainGrowReverse',
			animSpeed: 500,
			pauseTime: 5000,
			directionNav: false,
			controlNav: true,
			pauseOnHover: true
		});
	});
});

function animation(){
	newyear_takojai();
	newyear_takosune();
	newyear_nobitako();

	$("#"+mochi_id).css({
		"background":"url("+mochi_src+")",
		"width":mochi_width,
		"height":mochi_height
	});

	$("#"+nobi_id).css({
		"background":"url("+nobi_src+")",
		"width":nobi_width,
		"height":nobi_height
	});

	var interval = 1/fps*1000;
	animationInterval = setInterval(intervalEvent, interval);

	function intervalEvent(){
		$("#"+mochi_id).css({
			"background-position":-mochi_width * mochi_frame +"px 0"
		});
		mochi_frame++;
		if(mochi_frame>=mochi_max_frame){
			if(mochi_onceFlg) clearInterval( animationInterval );
			mochi_frame = 0;
		}
		
		$("#"+nobi_id).css({
			"background-position": nobi_bgposition +"px " + -nobi_height * nobi_frame +"px "
		});
		nobi_frame++;
		if(nobi_frame>=nobi_max_frame){
			if(nobi_onceFlg) clearInterval( animationInterval );
			nobi_frame = 0;
		}
	}
}

function newyear_takojai(){
	$("#newyear_takojai").animate({top:"+=12px",left:"-=7px"},1500,'easeInOutQuad').animate({top:"-=12px",left:"+=7px"}, 1500,'easeInOutQuad');
	setTimeout(function() {
		newyear_takojai();
	}, 3000);
}

function newyear_takosune(){
	$("#newyear_takosune").animate({top:"+=5px",left:"+=10px"},1500,'easeInOutQuad').animate({top:"-=5px",left:"-=10px"}, 1500,'easeInOutQuad');
	setTimeout(function() {
		newyear_takosune();
	}, 3000);
}

function newyear_nobitako(){
	$('#newyear_nobitako').delay(2000).animate({left:"-100%"},10000,'linear',function(){ nobi_bgposition = 460; })
	.delay(2000).animate({left:"150%"},10000,'linear',function(){ nobi_bgposition = 0; });
	setTimeout(function() {
		newyear_nobitako();
	}, 24000);
}

