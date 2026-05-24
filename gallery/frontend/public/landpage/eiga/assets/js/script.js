// jquery1.8.3.min.js (already included separately as jquery.min.js)

//////////////////////////////////
// ページ内リンクでアニメーション //
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
// マウスオーバーで画像が光る //
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
// スクロールでgoTop出現 //
/////////////////////////

$(function() {
var topBtn = $('#goTop');
topBtn.hide();
// スクロールが100に達したらボタン表示
$(window).scroll(function () {
if ($(this).scrollTop() > 100) {
topBtn.fadeIn();
} else {
topBtn.fadeOut();
}
});
// スクロールしてトップ
topBtn.click(function () {
$('body,html').animate({
scrollTop: 0
}, 500);
return false;
    });
});


//////////////////////////////////
// CSS Transform & Rotate Support //
//////////////////////////////////

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
        $el.css({
            '-webkit-transform': 'rotate(' + data.rotate + data.rotateUnits + ')',
            '-moz-transform': 'rotate(' + data.rotate + data.rotateUnits + ')',
            '-ms-transform': 'rotate(' + data.rotate + data.rotateUnits + ')',
            '-o-transform': 'rotate(' + data.rotate + data.rotateUnits + ')',
            'transform': 'rotate(' + data.rotate + data.rotateUnits + ')'
        });
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

    var curProxied = $.fx.prototype.cur;
    $.fx.prototype.cur = function () {
        if (this.prop == 'rotate') {
            return parseFloat($(this.elem).rotate());
        }
        return curProxied.apply(this, arguments);
    };
    
    $.fx.step.rotate = function (fx) {
        var data = initData($(fx.elem));
        $(fx.elem).rotate(fx.now + data.rotateUnits);
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

//////////////////////////////////
// Doraemon 16th Anniversary Animation //
//////////////////////////////////

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
    dm16_dora();
    dm16_gri();
    dm16_dorako();
}

function dm16_dora(){
    $("#dm16_dora").animate({rotate:"7deg"}, 800, "swing").animate({rotate:"0deg"}, 800, "swing");
    setTimeout(function() { dm16_dora(); }, 1600);
}

function dm16_gri(){
    $("#dm16_gri").animate({top:"-=30px", left:"+=18px"}, 1600, "swing").animate({top:"+=30px", left:"-=18px"}, 1600, "swing");
    setTimeout(function() { dm16_gri(); }, 3200);
}

function dm16_dorako(){
    $("#dm16_dorako").animate({top:"+=20px"}, 2000, "swing").animate({top:"-=20px"}, 2000, "swing");
    setTimeout(function() { dm16_dorako(); }, 4000);
}