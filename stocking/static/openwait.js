// Asking before the open image is replaced, and the files that wait for that question.
//
// Opening another image loses this one's regions and 走向 lines unless a file holds them, so the page asks first
// (ready). A file handed to the running tool from outside (dragged onto the desktop shortcut or start.bat, or named on
// the command line) cannot ask: it waits in the server, which tells every window (request, sync). Each window asks; the
// server takes the first answer only, and tells the others to stop asking (settle).
//
// What the server says about the waiting file carries a revision (rev). Events and answers to requests travel
// separately and can arrive out of order: anything older than what was already seen is ignored.
//
// The page gives the parts that touch the document, the dialog and the server:
//   latestDoc()      the open document's state as the server has it now, or null; rejects if the server does not say
//   shownDoc()       the document's state as last drawn here, or null
//   ask(doc)         show the dialog; resolves 'export', 'discard' or anything else for cancel
//   dismiss()        close the dialog as cancelled, if it is up
//   exportGuides()   export 丝袜引导.psd; resolves true once the file is written
//   pending()        {rev, file}: the file that waits ({id, path, name}) or null
//   take(id)         open the waiting file; resolves the new document's state, or {settled} if it no longer waits
//   cancel(id)       forget the waiting file
//   opening(name), opened(state), failed(error), done()   what to show while and after it opens
//   later(fn)        run fn after a short while (optional; tests give their own)

const PAGE = Symbol('page');            // the dialog is up for something the user did in this window
const RETRY = 3000;                     // ms before looking again at a file that could not be asked about

export function createReplaceGuard({ latestDoc, shownDoc, ask, dismiss, exportGuides, pending, take, cancel, opening, opened, failed, done,
  later = (fn) => setTimeout(fn, RETRY) }) {
  let chain = Promise.resolve();        // one question at a time: the dialog cannot be shown twice
  let owner = null;                     // whose dialog is up: PAGE, or the id of a waiting file
  let want = null;                      // the latest file that waits and is not answered here yet
  let answering = null;                 // id of the file whose answer is on its way to the server
  let handled = null;                   // id of the last file the server has taken an answer for from here
  let seen = -Infinity;                 // the newest revision heard of
  let running = false;
  let complained = null;                // id of the file whose failed question was already reported
  let retrying = false;

  // A request failed while a file may still wait, and nothing else will bring it up again (the event stream can stay
  // connected through one failed request): look again in a while.
  function retry() {
    if (retrying) return;
    retrying = true;
    later(() => {
      retrying = false;
      return sync();
    });
  }

  function queue(fn) {
    const p = chain.then(fn);
    chain = p.catch(() => {});
    return p;
  }

  function fresh(rev) {
    if (rev === undefined) return true;
    if (rev < seen) return false;
    seen = rev;
    return true;
  }

  // Resolves true to go ahead. stale(): the question is no longer worth asking (the file was settled meanwhile).
  async function decide(who, stale) {
    if (stale()) return false;
    let d;
    try {
      d = await latestDoc();            // the latest, not the last one drawn
    } catch (e) {
      // A waiting file opens on the server's word only: not knowing is not having nothing to lose. What the user
      // opens here goes by what is drawn here; that request fails by itself if the server is gone.
      if (who !== PAGE) throw e;
      d = shownDoc();
    }
    if (!d || !d.unsaved_guides) return true;
    if (stale()) return false;
    owner = who;
    let choice;
    try {
      choice = await ask(d);
    } finally {
      owner = null;
    }
    if (choice === 'discard') return true;
    if (choice === 'export') return exportGuides();
    return false;
  }

  async function run() {
    if (running) return;
    running = true;
    try {
      while (want) {
        const p = want;
        let go;
        try {
          go = await queue(() => decide(p.id, () => want !== p));
        } catch (e) {
          if (want === p) want = null;  // it still waits in the server
          if (complained !== p.id) {
            complained = p.id;
            failed(e);
          }
          retry();
          continue;
        }
        if (want !== p) continue;       // settled elsewhere, or a newer file took its place: nothing to send
        want = null;
        answering = p.id;
        let sent = false;
        try {
          if (!go) await cancel(p.id);
          else {
            opening(p.name);
            const st = await take(p.id);
            if (st && !st.settled) opened(st);
          }
          handled = p.id;
          sent = true;
        } catch (e) {
          failed(e);
        } finally {
          answering = null;
          done();
        }
        // A newer file this window has not heard of is taken up at once. After an answer that did not arrive the file
        // may still wait: in a while, not at once, or with nothing to lose (no dialog) the tries would never pause.
        if (sent) await sync();
        else retry();
      }
    } finally {
      running = false;
    }
  }

  function wait(p) {
    if (!p || p.id === handled || p.id === answering || (want && want.id === p.id)) return;
    want = p;
    if (owner !== null && owner !== PAGE) dismiss();   // a question about an older file: the server has forgotten it
    run();
  }

  function forget(id) {
    if (id === undefined) {             // nothing waits
      want = null;
      if (owner !== null && owner !== PAGE) dismiss();
    } else {                            // that file no longer waits
      if (want && want.id === id) want = null;
      if (owner === id) dismiss();
    }
  }

  // A file waits (the server's event).
  function request(p, rev) {
    if (fresh(rev)) wait(p);
  }

  // The file with this id no longer waits (answered in another window), or with no id nothing does (another image was
  // opened).
  function settle(id, rev) {
    if (fresh(rev)) forget(id);
  }

  // The event stream (re)connected, or an answer was sent: what waits now, as the server has it.
  async function sync() {
    let s;
    try {
      s = await pending();
    } catch {
      retry();
      return;
    }
    if (!s || !fresh(s.rev)) return;
    if (s.file) wait(s.file);
    else forget();
  }

  return { ready: () => queue(() => decide(PAGE, () => false)), request, settle, sync };
}
