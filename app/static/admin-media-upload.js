(function () {
  "use strict";

  const TUS_VERSION = "1.0.0";
  const RESUME_MAX_AGE = 23 * 60 * 60 * 1000;

  function text(el, value, kind) {
    if (!el) return;
    el.textContent = value;
    el.dataset.kind = kind || "info";
    el.hidden = false;
  }

  function progress(el, value) {
    if (!el) return;
    const safe = Math.max(0, Math.min(100, Number(value) || 0));
    el.hidden = false;
    const bar = el.querySelector("[data-upload-progress-bar]");
    const label = el.querySelector("[data-upload-progress-label]");
    if (bar) bar.style.width = safe.toFixed(1) + "%";
    if (label) label.textContent = Math.round(safe) + "%";
  }

  function parseJson(xhr) {
    try {
      return JSON.parse(xhr.responseText || "{}");
    } catch (_) {
      return {};
    }
  }

  function serverFormUpload(form, output, meter, button) {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action, true);
    xhr.timeout = 15 * 60 * 1000;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.addEventListener("progress", function (item) {
      if (item.lengthComputable) progress(meter, (item.loaded / item.total) * 100);
    });
    xhr.addEventListener("load", function () {
      const body = parseJson(xhr);
      if (xhr.status >= 200 && xhr.status < 300) {
        progress(meter, 100);
        text(output, body.message || "تم رفع الملف وربطه بالدرس بنجاح.", "success");
        window.setTimeout(function () {
          window.location.assign(body.return_to || window.location.href);
        }, 500);
        return;
      }
      text(output, body.detail || "تعذر رفع الملف. راجع النوع والحجم وإعداد التخزين.", "error");
      if (button) button.disabled = false;
    });
    xhr.addEventListener("timeout", function () {
      text(output, "استغرق الرفع وقتًا أطول من المتوقع. أعد المحاولة؛ الفيديوهات الكبيرة استخدم لها Stream القابل للاستكمال.", "error");
      if (button) button.disabled = false;
    });
    xhr.addEventListener("error", function () {
      text(output, "انقطع الاتصال أثناء رفع الملف. أعد المحاولة.", "error");
      if (button) button.disabled = false;
    });
    text(output, "جارٍ الرفع عبر المسار الاحتياطي… لا تغلق الصفحة.", "info");
    progress(meter, 0);
    xhr.send(new FormData(form));
  }

  function putDirect(url, file, contentType, meter) {
    return new Promise(function (resolve, reject) {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", url, true);
      xhr.timeout = 20 * 60 * 1000;
      xhr.setRequestHeader("Content-Type", contentType);
      xhr.upload.addEventListener("progress", function (item) {
        if (item.lengthComputable) progress(meter, (item.loaded / item.total) * 100);
      });
      xhr.addEventListener("load", function () {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error("r2_put_" + xhr.status));
      });
      xhr.addEventListener("timeout", function () { reject(new Error("r2_timeout")); });
      xhr.addEventListener("error", function () { reject(new Error("r2_network")); });
      xhr.send(file);
    });
  }

  async function directMediaUpload(form, file, csrf, output, meter) {
    const lesson = form.querySelector("select[name=lesson_id]");
    const lessonId = lesson && lesson.value;
    const initUrl = form.action.replace(/\/media$/, "/media-upload/init");
    const finalizeUrl = form.action.replace(/\/media$/, "/media-upload/finalize");
    text(output, "يتم تجهيز رفع مباشر وآمن إلى التخزين…", "info");
    const init = await appJson(initUrl, csrf, {
      lesson_id: Number(lessonId),
      file_name: file.name,
      file_size: file.size,
      content_type: file.type || "application/octet-stream",
    });
    let putFailure = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        await putDirect(init.upload_url, file, init.content_type, meter);
        putFailure = null;
        break;
      } catch (error) {
        putFailure = error;
        text(output, "تعذر جزء من الاتصال بالتخزين؛ محاولة " + (attempt + 2) + " من 3…", "info");
        await new Promise(function (resolve) { window.setTimeout(resolve, 800 * Math.pow(2, attempt)); });
      }
    }
    // A browser CORS/network error can hide a successful PUT response. Finalize
    // once before falling back; the server will verify object size/signature.
    try {
      const done = await appJson(finalizeUrl, csrf, { upload_token: init.upload_token });
      progress(meter, 100);
      return done;
    } catch (finalizeError) {
      if (!putFailure) throw finalizeError;
      putFailure.status = putFailure.status || finalizeError.status || 0;
      putFailure.serverMessage = finalizeError.message;
      throw putFailure;
    }
  }

  function formUpload(form) {
    const output = form.querySelector("[data-upload-message]");
    const meter = form.querySelector("[data-upload-progress]");
    const button = form.querySelector("button[type=submit],button:not([type])");
    const fileInput = form.querySelector("input[type=file]");
    const csrfInput = form.querySelector("input[name=csrf]");
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const file = fileInput && fileInput.files && fileInput.files[0];
      if (!file) return;
      if (button) button.disabled = true;
      progress(meter, 0);
      if (form.dataset.directMediaUpload === "1") {
        try {
          const body = await directMediaUpload(form, file, csrfInput.value, output, meter);
          text(output, body.message || "تم رفع الملف وربطه بالدرس بنجاح.", "success");
          window.setTimeout(function () { window.location.reload(); }, 500);
          return;
        } catch (error) {
          if ([400, 403, 413, 415].includes(Number(error.status || 0))) {
            text(output, error.message || "الملف غير صالح للرفع.", "error");
            if (button) button.disabled = false;
            return;
          }
          text(output, "تعذر الرفع المباشر؛ سيتم استخدام المسار الاحتياطي تلقائيًا.", "info");
        }
      }
      serverFormUpload(form, output, meter, button);
    });
  }

  function resumeKey(lessonId, file) {
    return ["mostashar-tus-v57", lessonId, file.name, file.size, file.lastModified].join(":");
  }

  function loadResume(key) {
    try {
      const item = JSON.parse(localStorage.getItem(key) || "null");
      if (!item || !item.uploadUrl || !item.uid || Date.now() - item.createdAt > RESUME_MAX_AGE) {
        localStorage.removeItem(key);
        return null;
      }
      return item;
    } catch (_) {
      localStorage.removeItem(key);
      return null;
    }
  }

  async function remoteOffset(uploadUrl) {
    const response = await fetch(uploadUrl, {
      method: "HEAD",
      headers: { "Tus-Resumable": TUS_VERSION },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("expired_upload");
    const value = Number(response.headers.get("Upload-Offset") || "0");
    if (!Number.isFinite(value) || value < 0) throw new Error("invalid_offset");
    return value;
  }

  function patchChunk(uploadUrl, chunk, offset, onProgress) {
    return new Promise(function (resolve, reject) {
      const xhr = new XMLHttpRequest();
      xhr.open("PATCH", uploadUrl, true);
      xhr.setRequestHeader("Tus-Resumable", TUS_VERSION);
      xhr.setRequestHeader("Upload-Offset", String(offset));
      xhr.setRequestHeader("Content-Type", "application/offset+octet-stream");
      xhr.upload.addEventListener("progress", function (item) {
        if (item.lengthComputable) onProgress(offset + item.loaded);
      });
      xhr.addEventListener("load", function () {
        if (xhr.status === 204) {
          const next = Number(xhr.getResponseHeader("Upload-Offset") || offset + chunk.size);
          resolve(Number.isFinite(next) ? next : offset + chunk.size);
        } else {
          reject(new Error("patch_" + xhr.status));
        }
      });
      xhr.addEventListener("error", function () { reject(new Error("network")); });
      xhr.send(chunk);
    });
  }

  async function uploadTus(item, file, chunkSize, key, onProgress, onResume) {
    let offset = 0;
    try {
      offset = await remoteOffset(item.uploadUrl);
      if (offset > 0) onResume(offset);
    } catch (_) {
      throw new Error("expired_upload");
    }
    while (offset < file.size) {
      const end = Math.min(offset + chunkSize, file.size);
      const chunk = file.slice(offset, end);
      let failure = null;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        try {
          offset = await patchChunk(item.uploadUrl, chunk, offset, function (loaded) {
            onProgress((loaded / file.size) * 100);
          });
          localStorage.setItem(key, JSON.stringify(item));
          failure = null;
          break;
        } catch (error) {
          failure = error;
          await new Promise(function (resolve) { window.setTimeout(resolve, 1000 * Math.pow(2, attempt)); });
          try {
            offset = await remoteOffset(item.uploadUrl);
            if (offset >= end) {
              failure = null;
              break;
            }
          } catch (_) {
            throw new Error("expired_upload");
          }
        }
      }
      if (failure) throw failure;
      onProgress((offset / file.size) * 100);
    }
  }

  async function appJson(url, csrf, body) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
      },
      body: JSON.stringify(body || {}),
    });
    const payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      const error = new Error(payload.detail || payload.error || "تعذر إكمال العملية.");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function streamUpload(form) {
    const lessonId = form.dataset.lessonId;
    const csrf = form.querySelector("input[name=csrf]").value;
    const fileInput = form.querySelector("input[type=file]");
    const output = form.querySelector("[data-upload-message]");
    const meter = form.querySelector("[data-upload-progress]");
    const button = form.querySelector("button[type=submit]");

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      const key = resumeKey(lessonId, file);
      if (button) button.disabled = true;
      text(output, "يتم تجهيز رابط رفع آمن…", "info");
      progress(meter, 0);
      try {
        let item = loadResume(key);
        let init = null;
        if (!item) {
          init = await appJson("/admin/lesson/" + lessonId + "/stream-upload/init", csrf, {
            file_name: file.name,
            file_size: file.size,
            content_type: file.type || "application/octet-stream",
          });
          item = {
            uploadUrl: init.upload_url,
            uid: init.uid,
            createdAt: Date.now(),
          };
          localStorage.setItem(key, JSON.stringify(item));
        }
        const chunkSize = (init && init.chunk_size) || (10 * 1024 * 1024);
        await uploadTus(
          item,
          file,
          chunkSize,
          key,
          function (value) { progress(meter, value); },
          function (offset) {
            text(output, "تم العثور على رفع سابق؛ يجري الاستكمال من " + Math.round((offset / file.size) * 100) + "%.", "info");
          }
        );
        progress(meter, 100);
        text(output, "اكتمل نقل الفيديو؛ يجري الآن تفعيل الحماية والمعالجة.", "info");
        const final = await appJson("/admin/lesson/" + lessonId + "/stream-upload/finalize", csrf, { uid: item.uid });
        localStorage.removeItem(key);
        text(output, final.message || "تم رفع المحاضرة وبدأت المعالجة.", final.state === "ready" ? "success" : "info");
        window.setTimeout(function () { window.location.reload(); }, 900);
      } catch (error) {
        if (error.message === "expired_upload") localStorage.removeItem(key);
        text(output, error.message || "تعذر رفع المحاضرة. يمكنك إعادة المحاولة وسيتم الاستكمال.", "error");
        if (button) button.disabled = false;
      }
    });
  }

  document.querySelectorAll("[data-media-upload-form]").forEach(formUpload);
  document.querySelectorAll("[data-stream-upload-form]").forEach(streamUpload);

  document.querySelectorAll("[data-stream-status-button]").forEach(function (button) {
    button.addEventListener("click", async function () {
      const output = document.querySelector("[data-stream-status-message]");
      button.disabled = true;
      try {
        const result = await appJson(
          "/admin/lesson/" + button.dataset.lessonId + "/stream-upload/status",
          button.dataset.csrf,
          { uid: button.dataset.uid }
        );
        text(output, result.message, result.state === "ready" ? "success" : (result.state === "error" ? "error" : "info"));
        if (result.state === "ready") window.setTimeout(function () { window.location.reload(); }, 700);
      } catch (error) {
        text(output, error.message || "تعذر تحديث حالة الفيديو.", "error");
      } finally {
        button.disabled = false;
      }
    });
  });
})();
