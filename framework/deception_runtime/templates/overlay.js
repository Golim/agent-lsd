/**
 * Runtime overlay rendering - canvas text drawing helper.
 */

(function(window) {
    'use strict';

    /**
     * Draw text on canvas at specified coordinates
     * @param {string} canvasId - Canvas element ID
     * @param {string} text - Text to draw (can be base64 encoded)
     * @param {Object} options - Drawing options
     */
    function drawCanvasText(canvasId, text, options) {
        options = options || {};

        var canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.warn('Canvas not found:', canvasId);
            return;
        }

        var ctx = canvas.getContext('2d');
        if (!ctx) {
            console.warn('Canvas context not available');
            return;
        }

        // Set canvas size to window size or specified dimensions
        canvas.width = options.width || window.innerWidth;
        canvas.height = options.height || window.innerHeight;

        // Decode text if base64 encoded
        var decodedText = text;
        if (options.encoded) {
            try {
                decodedText = atob(text);
            } catch (e) {
                console.warn('Failed to decode text:', e);
                decodedText = text;
            }
        }

        // Set drawing properties
        ctx.globalAlpha = options.opacity || 1.0;
        ctx.font = (options.fontSize || 18) + 'px ' + (options.fontFamily || 'monospace');
        ctx.fillStyle = options.color || '#000000';
        ctx.textBaseline = options.baseline || 'top';

        // Draw text at specified coordinates
        var x = options.x || 10;
        var y = options.y || 20;
        ctx.fillText(decodedText, x, y);
    }

    /**
     * Initialize canvas overlay after DOM is ready
     */
    function initializeOverlay() {
        // Reserved for future runtime hooks.
    }

    // Export to window for use by inline scripts
    window.RuntimeOverlay = {
        drawCanvasText: drawCanvasText,
        initialize: initializeOverlay
    };

})(window);
