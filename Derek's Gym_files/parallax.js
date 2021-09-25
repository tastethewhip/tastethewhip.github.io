;(function() {
  'use strict';

  var parallax;
  var attrName = 'data-background-parallax';
  var cssProperty = null;
  var frameRequestID = null;
  var scrollRatio = 0.2;

  var requestAnimationFramePolyfill = function() {
    /* jshint ignore:start */
    /**
     * requestAnimationFrame polyfill
     *
     * @author Erik Möller
     * @author Paul Irish
     * @author Tino Zijdel
     * @license MIT
     *
     * @see {@link https://gist.github.com/paulirish/1579671} for source
     * @see {@link http://paulirish.com/2011/requestanimationframe-for-smart-animating/} for description
     * @see {@link http://my.opera.com/emoller/blog/2011/12/20/requestanimationframe-for-smart-er-animating} for origin
     */
    !function(){for(var n=0,e=["ms","moz","webkit","o"],i=0;i<e.length&&!window.requestAnimationFrame;++i)window.requestAnimationFrame=window[e[i]+"RequestAnimationFrame"],window.cancelAnimationFrame=window[e[i]+"CancelAnimationFrame"]||window[e[i]+"CancelRequestAnimationFrame"];window.requestAnimationFrame||(window.requestAnimationFrame=function(e){var i=(new Date).getTime(),a=Math.max(0,16-(i-n)),o=window.setTimeout(function(){e(i+a)},a);return n=i+a,o}),window.cancelAnimationFrame||(window.cancelAnimationFrame=function(n){clearTimeout(n)})}();
    /* jshint ignore:end */
  };

  /** @see {@link http://stackoverflow.com/a/10965203} for source */
  var isIE9 = function() {
    var div = document.createElement('div');

    div.innerHTML = '<!--[if IE 9]><i></i><![endif]-->';

    return div.getElementsByTagName('i').length === 1;
  };

  // Determines whether any part of the container is in the viewport
  var isContainerInViewport = function(viewport, containerRect) {
    return (
      containerRect.top < viewport.height &&
      containerRect.left < viewport.width &&
      containerRect.bottom > 0 &&
      containerRect.right > 0
    );
  };

  // Determines if container entered from above the viewport
  var checkIfFromAbove = function(viewport, containerRect, prev) {
    if (containerRect.bottom < 0) {
      return true;
    }
    if (containerRect.top > viewport.height) {
      return false;
    }
    if (prev === undefined) {
      var overlapsBottomEdge = containerRect.top < viewport.height &&
        containerRect.bottom > viewport.height;
      return !overlapsBottomEdge;
    }
    return prev;
  };

  var getContainerElements = function() {
    var containers = document.querySelectorAll('[' + attrName + ']');

    return Array.prototype.slice.call(containers);
  };

  var getMaxOffset = function(context) {
    return context.background.el.offsetHeight - context.container.rect.height;
  };

  // Calculate Y-transformation of background image
  var getOffset = function(context) {
    if (context.container.fromAboveFold) {
      return context.container.rect.bottom * context.viewport.scrollRatio * -1;
    } else {
      return ((context.container.rect.top - context.viewport.height) *
        context.viewport.scrollRatio * -1) - context.maxOffset;
    }
  };

  var animateParallax = function(context) {
    context.maxOffset = getMaxOffset(context);
    var offset = getOffset(context);

    if (offset < -context.maxOffset) {
      offset = -context.maxOffset;
    } else if (offset > 0) {
      offset = 0;
    }

    context.background.el.style[cssProperty] = 'translateY(' + offset + 'px)';
    if (!context.background.el.style.opacity) {
      context.background.el.style.opacity = 1;
    }
  };

  var animateContainer = function(viewport, container) {
    var containerRect = container.el.getBoundingClientRect();

    container.fromAboveFold =
      checkIfFromAbove(viewport, containerRect, container.fromAboveFold);

    if (!isContainerInViewport(viewport, containerRect)) {
      return;
    }

    var context = {
      background: {
        el: container.el.querySelector('.parallax-bg'),
      },
      container: {
        el: container.el,
        rect: containerRect,
        fromAboveFold: container.fromAboveFold
      },
      viewport: viewport,
    };

    animateParallax(context);
  };

  var animateContainers = function() {
    var viewport = {
      width: window.innerWidth,
      height: window.innerHeight,
      scrollRatio: scrollRatio,
    };
    var animate = animateContainer.bind(null, viewport);

    parallax.containers.map(animate);
  };

  var startAnimating = function() {
    var animate = function() {
      animateContainers();
      frameRequestID = window.requestAnimationFrame(animate);
    };

    frameRequestID = window.requestAnimationFrame(animate);
  };

  var makeContainer = function(el) {
    return {
      el: el,
    };
  };

  var update = function() {
    cssProperty = isIE9() ? 'msTransform' : 'transform';
    parallax.containers = getContainerElements().map(makeContainer);
  };

  var start = function() {
    if (!frameRequestID) {
      startAnimating();
    }
  };

  var stop = function() {
    if (frameRequestID) {
      window.cancelAnimationFrame(frameRequestID);
      frameRequestID = null;
    }
  };

  var refresh = function() {
    parallax.update();

    if (parallax.containers.length) {
      parallax.start();
    } else {
      parallax.stop();
    }
  };

  parallax = {
    containers: [],
    requestAnimationFramePolyfill: requestAnimationFramePolyfill,
    refresh: refresh,
    start: start,
    stop: stop,
    update: update,
    checkIfFromAbove: checkIfFromAbove,
  };

  if (typeof module === 'object') {
    module.exports = parallax;
  } else {
    window.panelParallax = parallax;

    requestAnimationFramePolyfill();
    refresh();
  }
})();
