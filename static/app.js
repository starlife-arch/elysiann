// File drop preview
const photoInput = document.getElementById('photoInput');
const filePreview = document.getElementById('filePreview');
const fileDrop = document.getElementById('fileDrop');

if (photoInput && filePreview) {
  photoInput.addEventListener('change', () => {
    filePreview.innerHTML = '';
    Array.from(photoInput.files).slice(0, 5).forEach(file => {
      const reader = new FileReader();
      reader.onload = e => {
        const img = document.createElement('img');
        img.src = e.target.result;
        filePreview.appendChild(img);
      };
      reader.readAsDataURL(file);
    });
  });
}

// Drag-over visual feedback
if (fileDrop) {
  fileDrop.addEventListener('dragover', e => { e.preventDefault(); fileDrop.style.borderColor = 'var(--gold)'; });
  fileDrop.addEventListener('dragleave', () => { fileDrop.style.borderColor = ''; });
  fileDrop.addEventListener('drop', () => { fileDrop.style.borderColor = ''; });
}

// Auto-dismiss flash messages
document.querySelectorAll('.flash').forEach(el => {
  setTimeout(() => { el.style.transition = 'opacity 0.5s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 500); }, 4000);
});
