/**
 * File Picker Utility for GUI
 *
 * This module provides file picker functionality that allows users on network clients
 * to select local files and upload them to the host.
 */

/**
 * Opens a native file picker dialog and returns the selected file data
 * @param {Object} options - Options for the file picker
 * @param {string} options.accept - File type filter (e.g., '.yaml,.yml,.json')
 * @param {boolean} options.multiple - Allow multiple file selection (default: false)
 * @param {number} options.maxSize - Maximum file size in bytes (0 = no limit)
 * @returns {Promise<Object|null>} - File data with name, content (base64), size, type
 */
export function openFilePicker(options = {}) {
    return new Promise((resolve, reject) => {
        const input = document.createElement('input');
        input.type = 'file';
        input.style.display = 'none';

        if (options.accept) {
            input.accept = options.accept;
        }

        if (options.multiple) {
            input.multiple = true;
        }

        const maxSize = options.maxSize || 0;  // 0 = no limit

        let resolved = false;  // Prevent multiple resolutions

        // Handle file selection
        input.onchange = async () => {
            if (resolved) return;

            if (!input.files || input.files.length === 0) {
                resolved = true;
                resolve(null);
                return;
            }

            // Check file size if maxSize is specified
            if (maxSize > 0) {
                for (const file of input.files) {
                    if (file.size > maxSize) {
                        resolved = true;
                        const maxSizeStr = formatFileSize(maxSize);
                        const fileSizeStr = formatFileSize(file.size);
                        reject(new Error(`File "${file.name}" (${fileSizeStr}) exceeds maximum size of ${maxSizeStr}`));
                        if (document.body.contains(input)) {
                            document.body.removeChild(input);
                        }
                        return;
                    }
                }
            }

            try {
                if (options.multiple) {
                    const filesData = await Promise.all(
                        Array.from(input.files).map(file => readFileAsBase64(file))
                    );
                    resolved = true;
                    resolve(filesData);
                } else {
                    const fileData = await readFileAsBase64(input.files[0]);
                    resolved = true;
                    resolve(fileData);
                }
            } catch (error) {
                resolved = true;
                reject(error);
            } finally {
                if (document.body.contains(input)) {
                    document.body.removeChild(input);
                }
            }
        };

        // Handle cancel (user closes dialog without selecting)
        input.oncancel = () => {
            if (resolved) return;
            resolved = true;
            resolve(null);
            if (document.body.contains(input)) {
                document.body.removeChild(input);
            }
        };

        // For browsers that don't support oncancel, use focus event
        const handleFocus = () => {
            // Delay to allow onchange to fire first if a file was selected
            setTimeout(() => {
                if (resolved) return;
                if (!input.files || input.files.length === 0) {
                    resolved = true;
                    resolve(null);
                    if (document.body.contains(input)) {
                        document.body.removeChild(input);
                    }
                }
            }, 500);
        };

        window.addEventListener('focus', handleFocus, { once: true });

        document.body.appendChild(input);
        input.click();
    });
}

/**
 * Formats a file size in bytes to a human-readable string
 * @param {number} bytes - File size in bytes
 * @returns {string} - Formatted string (e.g., "1.5 MB")
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Reads a file and returns its content as base64
 * @param {File} file - The file to read
 * @returns {Promise<Object>} - File data object
 */
function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = () => {
            // Extract base64 content (remove data URL prefix)
            const base64Content = reader.result.split(',')[1];
            resolve({
                name: file.name,
                content: base64Content,
                size: file.size,
                type: file.type,
                lastModified: file.lastModified
            });
        };

        reader.onerror = () => {
            reject(new Error(`Failed to read file: ${file.name}`));
        };

        reader.readAsDataURL(file);
    });
}

/**
 * Reads a file and returns its content as text
 * @param {File} file - The file to read
 * @returns {Promise<Object>} - File data object with text content
 */
export function readFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = () => {
            resolve({
                name: file.name,
                content: reader.result,
                size: file.size,
                type: file.type,
                lastModified: file.lastModified
            });
        };

        reader.onerror = () => {
            reject(new Error(`Failed to read file: ${file.name}`));
        };

        reader.readAsText(file);
    });
}
