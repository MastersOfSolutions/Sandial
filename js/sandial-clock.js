// Sandial clock logic
var calibrateTimer = null;
var tickTimer = null;
var clockEl;
var inBG = 0;

function stopClock() {
  if (tickTimer !== null) {
    window.clearInterval(tickTimer);
    return true;
  }
  return false;
}

function validateClock() {
  var dateNow = new Date();
  var clockImgSrcNow = clockSrcFormat(dateNow.getHours(), dateNow.getMinutes());
  return clockImgSrcNow == clockEl.getAttribute("data");
}

function startClock() {
  stopClock();
  if (calibrateTimer !== null) {
    window.clearTimeout(calibrateTimer);
  }
  clockTick();
  tickTimer = window.setInterval(clockTick, 60000);
}

function calibrate() {
  console.log("Calibrating the clock.");
  clockEl = document.getElementById("sandial-clock-img");
  var msOffset = (60 - new Date().getSeconds()) * 1000;
  calibrateTimer = window.setTimeout(startClock, msOffset);
  clockTick();
}

function clockSrcFormat(hourInt, minsInt) {
  var hourStr = (hourInt < 10) ? "0" + hourInt.toString() : hourInt.toString();
  var minsStr = (minsInt < 10) ? "0" + minsInt.toString() : minsInt.toString();
  return "clocks/clock_" + hourStr + "_" + minsStr + ".svg";
}

function clockTick() {
  var dateNow = new Date();
  var clockImgSrc = clockSrcFormat(dateNow.getHours(), dateNow.getMinutes());
  console.log("Changing clock to " + clockImgSrc);
  clockEl.setAttribute("data", clockImgSrc);
  clockEl.type = "foo"; // Invalidate the rendered object
  clockEl.type = "image/svg+xml";
  
}

function handleOnblur(blurEvt) {
  inBG++;
}

function handleOnFocus(focusEvt) {
  if (inBG > 0) {
    console.log("Focus regained. Validating that we didn't fall out of sync while in background.");
    inBG = 0;
    if (!validateClock()) {
      calibrate();
    }
    else {
      console.log("Everything looks okay.");
    }
  }
  
}

calibrate();

document.body.onfocus = handleOnFocus;
document.body.onblur = handleOnblur;
