document.getElementById('actionBtn').addEventListener('click', function() {
  const messageDiv = document.getElementById('message');
  const now = new Date().toLocaleTimeString();
  messageDiv.textContent = `Button clicked at ${now}!`;
  messageDiv.style.color = '#4CAF50';
});
