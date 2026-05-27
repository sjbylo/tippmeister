// Der Tippmeister - Client-side JavaScript

(function() {
	'use strict';

	// Convert UTC times to user's local timezone
	function convertTimezones() {
		var elements = document.querySelectorAll('[data-utc]');
		elements.forEach(function(el) {
			var utc = el.getAttribute('data-utc');
			if (!utc) return;

			try {
				var date = new Date(utc);
				if (isNaN(date.getTime())) return;

				var userTz = document.body.getAttribute('data-timezone') || undefined;
				var options = {
					month: 'short',
					day: 'numeric',
					hour: '2-digit',
					minute: '2-digit',
					hour12: false,
					timeZoneName: 'short',
				};
				if (userTz) {
					options.timeZone = userTz;
				}

				el.textContent = date.toLocaleString(undefined, options);
			} catch(e) {
				// keep original text on error
			}
		});
	}

	// Auto-dismiss flash messages after 5 seconds
	function setupFlashDismiss() {
		var flashes = document.querySelectorAll('.flash');
		flashes.forEach(function(flash) {
			setTimeout(function() {
				flash.style.opacity = '0';
				flash.style.transition = 'opacity 0.5s';
				setTimeout(function() { flash.remove(); }, 500);
			}, 5000);
		});
	}

	document.addEventListener('DOMContentLoaded', function() {
		convertTimezones();
		setupFlashDismiss();
	});
})();
