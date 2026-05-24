/////////////////////
//TOPアニメーション//
/////////////////////

$(document).ready(function() {
    setTimeout(animation, 300);
    
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
balloon();
adballoon();
dora();
cloud1();
cloud2();
cloud3();
cloud4();
cloud5();
}

function balloon(){
    $("#top_anniv_balloon").animate({top:"-=10px"}, 2000, 'swing').animate({top:"+=10px"}, 2000, 'swing');
    setTimeout(balloon, 2000);
}

function adballoon(){
    $("#top_anniv_adballoon1").animate({rotate:"3deg"}, 3000, 'swing').animate({rotate:"0deg"}, 3000, 'swing');
    $("#top_anniv_adballoon2").animate({rotate:"3deg"}, 3000, 'swing').animate({rotate:"0deg"}, 3000, 'swing');
    setTimeout(adballoon, 6000);
}

function dora(){
    $("#top_anniv_dora").animate({rotate:"10deg"}, 500, 'swing').animate({rotate:"0deg"}, 500, 'swing');
    $("#top_anniv_minidora").animate({rotate:"10deg"}, 500, 'swing').animate({rotate:"0deg"}, 500, 'swing');
    setTimeout(dora, 1000);
}

var cloudWidth = Math.floor($(window).width() + 600);

function cloud1(){
    $("#cloud1").animate({left: cloudWidth}, 65000, 'linear').animate({left: "-300px"}, 0);
    setTimeout(cloud1, 1000);
}

function cloud2(){
    $("#cloud2").animate({left: cloudWidth}, 62000, 'linear').animate({left: "-150px"}, 0);
    setTimeout(cloud2, 1000);
}

function cloud3(){
    $("#cloud3").animate({left: cloudWidth}, 34000, 'linear').animate({left: "-100px"}, 0);
    setTimeout(cloud3, 1000);
}

function cloud4(){
    $("#cloud4").animate({left: cloudWidth}, 40000, 'linear').animate({left: "-150px"}, 0);
    setTimeout(cloud4, 1000);
}

function cloud5(){
    $("#cloud5").animate({left: cloudWidth}, 58000, 'linear').animate({left: "-200px"}, 0);
    setTimeout(cloud5, 1000);
}

$(function() {
	$('#top_anniv_doraLink')
	.hover(
		function(){
			$('#top_anniv_hukidashi').show();
		},
		function () {
			$('#top_anniv_hukidashi').hide();
		}
	);
});


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



//////////////////////////////////////////
//Santa Sori Moving Effect (Right to Left)//
//////////////////////////////////////////

$(document).ready(function(){
	// Animate the existing santa_sori element
	animateExistingSantaSori();
	// Start smooth minidora animation
	santa_minidora_smooth();
	// Initialize snowfall effect
	initSnowfall();
});

function animateExistingSantaSori() {
	var windowWidth = $(window).width();
	
	// Start position (far right, outside screen)
	var startX = windowWidth + 50;
	
	// End position (far left, outside screen)  
	var endX = -150;
	
	// Set initial position
	$('#santa_sori').css('right', '-100px');
	
	// Animate from right to left slowly (30 seconds)
	$('#santa_sori').animate({
		right: windowWidth + 150 + 'px'
	}, 30000, 'linear', function() {
		// Animation complete, restart after a short delay
		setTimeout(function() {
			// Reset position and restart
			$('#santa_sori').css('right', '-100px');
			animateExistingSantaSori();
		}, 3000); // 3 second delay before restarting
	});
}

// Smooth minidora animation using jQuery (copied from normal folder)
function santa_minidora_smooth(){
    $("#santa_minidora").animate({top:"-=15px"}, 1000, 'easeInOutSine').animate({top:"+=15px"}, 1000, 'easeInOutSine');
    setTimeout(santa_minidora_smooth, 1000);
}

// Enhanced Christmas Snowfall Effect with optimized performance
function initSnowfall() {
	var flakes = [];
	var flakeCount = 100; // Increased to match optimized performance
	var isTabActive = true;
	
	// Performance optimization - pause when tab is not active
	document.addEventListener('visibilitychange', function() {
		isTabActive = !document.hidden;
	});
	
	function random(min, max) {
		return Math.round(min + Math.random()*(max-min));
	}
	
	function createFlake(id) {
		var elWidth = $(window).width();
		var elHeight = $(window).height();
		var x = random(0, elWidth);
		var y = random(-100, -10);
		var size = random(11, 18); // Match optimized size range
		var speed = random(8, 30) / 10; // Match optimized speed range (0.8-3.0)
		var stepSize = random(1, 10) / 100;
		var step = 0;
		var opacity = random(0.4, 1.0);
		var rotation = random(0, 360);
		var rotationSpeed = random(-2, 2);
		var isSparkle = random(1, 10) <= 2; // 20% chance for sparkle effect
		
		// Create snowflake using CSS
		var flake = $('<div>')
			.attr('id', 'snowflake-' + id)
			.addClass('snowflake' + (isSparkle ? ' sparkle' : ''))
			.css({
				'position': 'fixed',
				'top': y + 'px',
				'left': x + 'px',
				'width': size + 'px',
				'height': size + 'px',
				'background': isSparkle ? 'radial-gradient(circle, #FFF, #E0E0FF)' : '#FFF',
				'border-radius': '50%',
				'opacity': opacity,
				'z-index': 999,
				'pointer-events': 'none',
				'box-shadow': isSparkle ? '0 0 8px rgba(255,255,255,0.9), 0 0 15px rgba(224,224,255,0.5)' : '0 0 3px rgba(255,255,255,0.6)',
				'transform': 'rotate(' + rotation + 'deg)',
				'-moz-transform': 'rotate(' + rotation + 'deg)',
				'-webkit-transform': 'rotate(' + rotation + 'deg)'
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
			rotation: rotation,
			rotationSpeed: rotationSpeed,
			update: function() {
				this.y += this.speed;
				
				if (this.y > $(window).height() + 20) {
					this.reset();
				}
				
				// Enhanced physics with horizontal drift
				this.step += this.stepSize;
				this.x += Math.cos(this.step);
				this.rotation += this.rotationSpeed;
				
				if (this.x > $(window).width() - 22 || this.x < 22) {
					this.reset();
				}
				
				// Update position and rotation
				this.element.css({
					'top': this.y + 'px',
					'left': this.x + 'px',
					'transform': 'rotate(' + this.rotation + 'deg)',
					'-moz-transform': 'rotate(' + this.rotation + 'deg)',
					'-webkit-transform': 'rotate(' + this.rotation + 'deg)'
				});
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
	
	// Create snowflakes
	for (var i = 0; i < flakeCount; i++) {
		flakes.push(createFlake(i));
	}
	
	// Optimized animation loop matching legacy timing (30ms)
	function animate() {
		if (isTabActive) {
			for (var i = 0; i < flakes.length; i++) {
				flakes[i].update();
			}
		}
		setTimeout(animate, 30); // Match optimized 30ms timing
	}
	
	animate();
	
	// Handle window resize
	$(window).resize(function() {
		// Reset snowflakes positions on resize
		for (var i = 0; i < flakes.length; i++) {
			if (flakes[i].x > $(window).width()) {
				flakes[i].x = random(0, $(window).width());
			}
		}
	});
	
	// Create occasional bursts of extra snowflakes
	setInterval(function() {
		if (random(1, 10) <= 3) { // 30% chance every 5 seconds
			var burstCount = random(5, 15);
			for (var i = 0; i < burstCount; i++) {
				var tempFlake = createFlake('burst-' + Date.now() + '-' + i);
				setTimeout(function(flake) {
					return function() {
						flake.element.fadeOut(2000, function() {
							flake.element.remove();
						});
					};
				}(tempFlake), random(8000, 15000));
			}
		}
	}, 5000);
}