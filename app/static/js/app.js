// Der Tippmeister - Client-side JavaScript

(function() {
	'use strict';

	var i18n = {};
	try {
		var el = document.getElementById('i18n-data');
		if (el) i18n = JSON.parse(el.textContent);
	} catch(e) {}
	function t(key, fallback) { return i18n[key] || fallback || key; }

	// Convert UTC times to user's local timezone
	function convertTimezones() {
		var elements = document.querySelectorAll('[data-utc]');
		elements.forEach(function(el) {
			var utc = el.getAttribute('data-utc');
			if (!utc) return;

			try {
				if (!/[Z]$/.test(utc) && !/[+-]\d{2}:\d{2}$/.test(utc)) utc += 'Z';
				var date = new Date(utc);
				if (isNaN(date.getTime())) return;

				var userTz = document.body.getAttribute('data-timezone') || undefined;
			var options = {
				month: 'short',
				day: 'numeric',
				hour: '2-digit',
				minute: '2-digit',
				hour12: false,
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

	function startNowBar() {
		var bar = document.getElementById('now-bar');
		if (!bar) return;
		var tz = document.body.getAttribute('data-timezone') || Intl.DateTimeFormat().resolvedOptions().timeZone;
		var warp = document.body.getAttribute('data-warp');
		var suffix = ' &mdash; <a href="/profile" class="local-time-link">' + t('allTimesLocal', 'all times local') + '</a>';

		if (warp) {
			var warpDate = new Date(warp.indexOf('Z') < 0 && warp.indexOf('+') < 0 ? warp + 'Z' : warp);
			var opts = {
				weekday: 'short', month: 'short', day: 'numeric',
				hour: '2-digit', minute: '2-digit', second: '2-digit',
				hour12: false, timeZone: tz
			};
			bar.innerHTML = '<span class="warp-badge">' + t('timeWarp', 'TIME WARP') + '</span> ' +
				warpDate.toLocaleString(undefined, opts) + suffix;
			return;
		}

		function tick() {
			var now = new Date();
			var opts = {
				weekday: 'short', month: 'short', day: 'numeric',
				hour: '2-digit', minute: '2-digit', second: '2-digit',
				hour12: false, timeZone: tz
			};
			bar.innerHTML = now.toLocaleString(undefined, opts) + suffix;
		}
		tick();
		setInterval(tick, 1000);
	}

	function setupOthersToggle() {
		var toggles = document.querySelectorAll('.others-toggle');
		if (!toggles.length) return;
		var shown = false;
		toggles.forEach(function(btn) {
			btn.addEventListener('click', function(e) {
				e.preventDefault();
				e.stopPropagation();
				shown = !shown;
				var allOthers = document.querySelectorAll('.pred-row-others');
				allOthers.forEach(function(el) { el.style.display = shown ? '' : 'none'; });
				toggles.forEach(function(t) { t.classList.toggle('open', shown); });
			});
		});
	}

	// Prediction modal
	var modal = null;
	var modalMatchId = null;
	var modalSourceEl = null;
	var modalSaveAndNext = false;

	function getCSRFToken() {
		var meta = document.querySelector('meta[name="csrf-token"]');
		return meta ? meta.getAttribute('content') : '';
	}

	function getUntippedCards() {
		return Array.from(document.querySelectorAll('.match-card-predict')).filter(function(card) {
			var scoreEl = card.querySelector('.own-pred .pred-score');
			return scoreEl && scoreEl.classList.contains('no-pred');
		});
	}

	function openPredModal(matchId, team1, team2, isKnockout, curT1, curT2, curPen, sourceEl) {
		modal = document.getElementById('pred-modal');
		if (!modal) return;
		modalMatchId = matchId;
		modalSourceEl = sourceEl || null;

		document.getElementById('modal-title').textContent = team1 + ' ' + t('vs', 'vs') + ' ' + team2;
		document.getElementById('modal-team1').textContent = team1;
		document.getElementById('modal-team2').textContent = team2;
		document.getElementById('modal-t1').value = curT1 !== null && curT1 !== '' ? curT1 : '';
		document.getElementById('modal-t2').value = curT2 !== null && curT2 !== '' ? curT2 : '';
		document.getElementById('modal-error').style.display = 'none';

		var penRow = document.getElementById('modal-pen-row');
		var penSelect = document.getElementById('modal-pen');
		if (isKnockout) {
			penSelect.innerHTML = '<option value="">' + t('select', '-- Select --') + '</option>' +
				'<option value="' + team1 + '">' + team1 + '</option>' +
				'<option value="' + team2 + '">' + team2 + '</option>';
			if (curPen) penSelect.value = curPen;
			checkModalDraw();
			penRow.dataset.knockout = 'true';
		} else {
			penRow.style.display = 'none';
			penRow.dataset.knockout = 'false';
		}

		// Show/hide Save & Next based on remaining untipped cards
		var saveNextBtn = document.getElementById('modal-save-next');
		if (saveNextBtn) {
			var untipped = getUntippedCards();
			var hasNext = untipped.some(function(c) { return c.dataset.matchId !== String(matchId); });
			saveNextBtn.style.display = hasNext ? '' : 'none';
		}

		modal.style.display = 'flex';
		document.getElementById('modal-t1').focus();
	}

	function closeModal() {
		if (modal) modal.style.display = 'none';
		modalMatchId = null;
		modalSourceEl = null;
		modalSaveAndNext = false;
	}

	function checkModalDraw() {
		var penRow = document.getElementById('modal-pen-row');
		if (penRow.dataset.knockout !== 'true') return;
		var t1 = document.getElementById('modal-t1').value;
		var t2 = document.getElementById('modal-t2').value;
		if (t1 !== '' && t2 !== '' && parseInt(t1) === parseInt(t2)) {
			penRow.style.display = 'flex';
			penRow.classList.add('pen-highlight');
		} else {
			penRow.style.display = 'none';
			penRow.classList.remove('pen-highlight');
		}
	}

	function saveModal(andNext) {
		var t1 = document.getElementById('modal-t1').value;
		var t2 = document.getElementById('modal-t2').value;
		var penRow = document.getElementById('modal-pen-row');
		var pen = '';
		if (penRow.dataset.knockout === 'true' && penRow.style.display !== 'none') {
			pen = document.getElementById('modal-pen').value;
			if (!pen) {
				showModalError(t('selectPenaltyWinner', 'Please select which team wins on penalties!'));
				penRow.classList.add('pen-error');
				return;
			}
		}

		if (t1 === '' || t2 === '') {
			showModalError(t('enterBothScores', 'Please enter both scores.'));
			return;
		}

		var payload = {
			team1_score: parseInt(t1),
			team2_score: parseInt(t2),
			penalty_winner: pen
		};

		var saveBtn = document.getElementById('modal-save');
		var saveNextBtn = document.getElementById('modal-save-next');
		saveBtn.disabled = true;
		if (saveNextBtn) saveNextBtn.disabled = true;
		saveBtn.textContent = '...';

		var currentMatchId = modalMatchId;

		fetch('/predict/' + modalMatchId, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'X-CSRFToken': getCSRFToken()
			},
			body: JSON.stringify(payload)
		}).then(function(resp) {
			return resp.json();
		}).then(function(data) {
			saveBtn.disabled = false;
			if (saveNextBtn) saveNextBtn.disabled = false;
			saveBtn.textContent = t('save', 'Save');
			if (data.success) {
				if (modalSourceEl) {
					modalSourceEl.innerHTML = t1 + '-' + t2;
					if (pen) modalSourceEl.innerHTML += '<small>(' + pen.substring(0, 3) + ')</small>';
					modalSourceEl.classList.remove('no-pred');
				}
				// Remove the Enter Tip button from this card
				var card = document.querySelector('.match-card-predict[data-match-id="' + currentMatchId + '"]');
				if (card) {
					var enterBtn = card.querySelector('.btn-enter-tip');
					if (enterBtn) enterBtn.remove();
				}

				if (andNext) {
					openNextUntipped(currentMatchId);
				} else {
					closeModal();
					showSavedFlash(card || modalSourceEl);
				}
			} else {
				showModalError(data.error || t('saveFailed', 'Save failed.'));
			}
		}).catch(function() {
			saveBtn.disabled = false;
			if (saveNextBtn) saveNextBtn.disabled = false;
			saveBtn.textContent = t('save', 'Save');
			showModalError(t('networkError', 'Network error. Please try again.'));
		});
	}

	function openNextUntipped(currentMatchId) {
		var untipped = getUntippedCards().filter(function(c) {
			return c.dataset.matchId !== String(currentMatchId);
		});
		if (untipped.length > 0) {
			var next = untipped[0];
			var d = next.dataset;
			openPredModal(
				d.matchId, d.team1, d.team2,
				d.knockout === 'true',
				d.curT1 || '', d.curT2 || '', d.curPen || '',
				next.querySelector('.own-pred .pred-score')
			);
		} else {
			closeModal();
		}
	}

	function showSavedFlash(nearEl) {
		if (!nearEl) return;
		var flash = document.createElement('span');
		flash.className = 'save-flash';
		flash.textContent = t('saved', 'Saved!');
		nearEl.closest('.match-card, .pred-cell') && nearEl.closest('.match-card, .pred-cell').appendChild(flash);
		if (!flash.parentElement) nearEl.appendChild(flash);
		setTimeout(function() { flash.classList.add('fade-out'); }, 1200);
		setTimeout(function() { flash.remove(); }, 1800);
	}

	function showModalError(msg) {
		var errEl = document.getElementById('modal-error');
		errEl.textContent = msg;
		errEl.style.display = 'block';
	}

	function setupModal() {
		if (!document.getElementById('pred-modal')) return;

		document.getElementById('modal-save').addEventListener('click', function() { saveModal(false); });
		var saveNextBtn = document.getElementById('modal-save-next');
		if (saveNextBtn) {
			saveNextBtn.addEventListener('click', function() { saveModal(true); });
		}
		document.getElementById('modal-cancel').addEventListener('click', closeModal);
		document.getElementById('modal-backdrop').addEventListener('click', closeModal);
		document.getElementById('modal-t1').addEventListener('input', checkModalDraw);
		document.getElementById('modal-t2').addEventListener('input', checkModalDraw);

		document.addEventListener('keydown', function(e) {
			if (e.key === 'Escape' && modal && modal.style.display !== 'none') {
				closeModal();
			}
			if (e.key === 'Enter' && modal && modal.style.display !== 'none') {
				e.preventDefault();
				saveModal(false);
			}
		});

		// Grid cells
		document.querySelectorAll('.pred-modal-trigger').forEach(function(cell) {
			cell.addEventListener('click', function(e) {
				e.preventDefault();
				e.stopPropagation();
				var d = this.dataset;
				openPredModal(
					d.matchId, d.team1, d.team2,
					d.knockout === 'true',
					d.curT1 || '', d.curT2 || '', d.curPen || '',
					this
				);
			});
		});

		// Match cards
		document.querySelectorAll('.match-card-predict').forEach(function(card) {
			card.addEventListener('click', function(e) {
				if (e.target.closest('.others-toggle') || e.target.closest('.pred-row-others')) return;
				e.preventDefault();
				var d = this.dataset;
				openPredModal(
					d.matchId, d.team1, d.team2,
					d.knockout === 'true',
					d.curT1 || '', d.curT2 || '', d.curPen || '',
					this.querySelector('.own-pred .pred-score')
				);
			});
		});
	}

	// Per-row AJAX save on My Tips page (auto-save)
	function setupInlineSave() {
		var form = document.getElementById('predictionsForm');
		if (!form) return;

		var rows = form.querySelectorAll('.pred-row');
		rows.forEach(function(row) {
			var matchId = row.dataset.matchId;
			if (!matchId) return;

			var t1Input = row.querySelector('[name="t1_' + matchId + '"]');
			var t2Input = row.querySelector('[name="t2_' + matchId + '"]');
			if (!t1Input || !t2Input) return;

			var statusEl = document.createElement('span');
			statusEl.className = 'row-status';
			var inputRow = row.querySelector('.pred-input-row');
			inputRow.appendChild(statusEl);

			var saveTimeout = null;

			function trySave() {
				var t1 = t1Input.value;
				var t2 = t2Input.value;
				if (t1 === '' || t2 === '') return;

				var pen = '';
				var penSelect = row.querySelector('.pen-select');
				var isKnockout = row.dataset.knockout === 'true';
				if (isKnockout && parseInt(t1) === parseInt(t2)) {
					pen = penSelect ? penSelect.value : '';
					if (!pen) return;
				}

				statusEl.textContent = '...';
				statusEl.className = 'row-status saving';

				fetch('/predict/' + matchId, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						'X-CSRFToken': getCSRFToken()
					},
					body: JSON.stringify({
						team1_score: parseInt(t1),
						team2_score: parseInt(t2),
						penalty_winner: pen
					})
				}).then(function(r) { return r.json(); })
				.then(function(data) {
					if (data.success) {
						statusEl.textContent = '\u2713';
						statusEl.className = 'row-status saved';
						row.classList.add('row-saved');
					} else {
						statusEl.textContent = '\u2717';
						statusEl.className = 'row-status error';
					}
				}).catch(function() {
					statusEl.textContent = '\u2717';
					statusEl.className = 'row-status error';
				});
			}

			function debounceSave() {
				if (saveTimeout) clearTimeout(saveTimeout);
				saveTimeout = setTimeout(trySave, 600);
			}

			t1Input.addEventListener('input', debounceSave);
			t2Input.addEventListener('input', debounceSave);
			var penSelect = row.querySelector('.pen-select');
			if (penSelect) penSelect.addEventListener('change', debounceSave);
		});

		// Hide the bulk submit button
		var bulkSubmit = form.querySelector('.form-actions');
		if (bulkSubmit) bulkSubmit.style.display = 'none';
	}

	// Expose for inline use
	window.openPredModal = openPredModal;

	document.addEventListener('DOMContentLoaded', function() {
		convertTimezones();
		setupFlashDismiss();
		startNowBar();
		setupOthersToggle();
		setupModal();
		setupInlineSave();
	});
})();
