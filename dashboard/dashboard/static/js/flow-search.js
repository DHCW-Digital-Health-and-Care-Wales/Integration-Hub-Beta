// Flow search picker: a datalist-backed text input that resolves the chosen
// option to a flow id in the hidden `flow` field and submits the GET form.
// Forms opt in with `data-flow-search`; `data-allow-custom="true"` lets an
// unmatched typed value be submitted as a new workflow id.
(function () {
  'use strict';

  function wire(form) {
    var input = form.querySelector('.js-flow-search');
    var hidden = form.querySelector('input[type="hidden"][name="flow"]');
    var list = input && document.getElementById(input.getAttribute('list'));
    if (!input || !hidden || !list) return;
    var allowCustom = form.getAttribute('data-allow-custom') === 'true';

    function flowIdFor(value) {
      var options = list.getElementsByTagName('option');
      for (var i = 0; i < options.length; i++) {
        if (options[i].value === value) return options[i].getAttribute('data-flow-id');
      }
      return null;
    }

    input.addEventListener('input', function () {
      var flowId = flowIdFor(input.value);
      if (flowId && flowId !== hidden.value) {
        hidden.value = flowId;
        form.submit();
      }
    });

    // The datalist popup can swallow Enter, so submit explicitly.
    input.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      form.requestSubmit();
    });

    form.addEventListener('submit', function (e) {
      var flowId = flowIdFor(input.value) || (allowCustom ? input.value.trim() : null);
      if (!flowId) { e.preventDefault(); return; }
      hidden.value = flowId;
    });
  }

  document.querySelectorAll('form[data-flow-search]').forEach(wire);
})();
