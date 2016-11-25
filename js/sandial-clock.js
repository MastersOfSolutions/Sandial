// Sandial clock logic
var startTimeout;
var clockEl;

function startClock() {
  window.clearTimeout(startTimeout);
  clockTick();
  window.setTimeout(clockTick, 60000);
}

function calibrate() {
  clockEl = document.getElementById("sandial-clock-img");
  var msOffset = (60 - new Date().getSeconds()) * 1000;
  startTimeout = window.setTimeout(startClock, msOffset);
  clockTick();
}

function clockTick() {
  var dateNow = new Date();
  var hourNow = dateNow.getHours();
  var minsNow = dateNow.getMinutes();
  var hourStr = hourNow.toString();
  if (hourNow < 10) {
    hourStr = "0" + hourStr;
  }
  var minsStr = minsNow.toString();
  if (minsNow < 10) {
    minsStr = "0" + minsStr;
  }
  
  var clockImgSrc = "clocks/clock_" + hourStr + "_" + minsStr + ".svg";
  clockEl.src = clockImgSrc;
}

calibrate();
