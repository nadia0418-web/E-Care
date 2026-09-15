// E-Care 프론트엔드 스크립트

// Double-check 항목이 모두 체크되어야만 "이메일 전송" 버튼을 활성화한다.
// (서버에서도 동일하게 재검증하므로, 이 스크립트는 UX 보조용이다.)
document.addEventListener("DOMContentLoaded", function () {
    var checkboxes = document.querySelectorAll(".dc-item");
    var sendBtn = document.getElementById("send-email-btn");
    if (!checkboxes.length || !sendBtn) return;

    function refresh() {
        var allChecked = Array.prototype.every.call(checkboxes, function (cb) {
            return cb.checked;
        });
        sendBtn.disabled = !allChecked;
    }

    checkboxes.forEach(function (cb) {
        cb.addEventListener("change", refresh);
    });
    refresh();
});
