document.addEventListener("DOMContentLoaded", () => {
  // 1. Live Table Search Filtering
  const searchInput = document.getElementById("tableSearch");
  if (searchInput) {
    searchInput.addEventListener("keyup", (e) => {
      const term = e.target.value.toLowerCase();
      const rows = document.querySelectorAll("tbody tr");
      rows.forEach((row) => {
        const text = row.innerText.toLowerCase();
        row.style.display = text.includes(term) ? "" : "none";
      });
    });
  }

  // 2. Client-Side Time & Date Minimum Restriction
  const dateInput = document.querySelector('input[type="date"]');
  if (dateInput) {
    const today = new Date().toISOString().split("T")[0];
    dateInput.setAttribute("min", today);
  }

  // 3. One-Click Copy to Clipboard for API Keys
  const copyButtons = document.querySelectorAll(".btn-copy-token");
  copyButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const token = btn.getAttribute("data-token");
      navigator.clipboard.writeText(token).then(() => {
        const originalText = btn.innerText;
        btn.innerText = "Copied!";
        btn.style.color = "#16a34a";
        setTimeout(() => {
          btn.innerText = originalText;
          btn.style.color = "";
        }, 1800);
      });
    });
  });

  // 4. Client Notification Toast Dispatcher
  window.showToast = function(title, message, isEmergency = false) {
    const toast = document.getElementById("notification-toast");
    if (!toast) return;
    toast.style.display = "block";
    toast.style.borderLeftColor = isEmergency ? "#e11d48" : "#0284c7";
    toast.innerHTML = `
      <div style="font-weight: 700; color: ${isEmergency ? '#e11d48' : '#0284c7'}">${title}</div>
      <div style="font-size: 0.85rem; color: #475569; margin-top: 4px;">${message}</div>
    `;
    setTimeout(() => {
      toast.style.display = "none";
    }, 4500);
  };
});