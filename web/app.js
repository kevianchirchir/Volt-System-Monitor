
/* ============================================
   DOM HELPERS
============================================ */

const $ = (selector, root = document) =>
    root.querySelector(selector);

const $$ = (selector, root = document) =>
    [...root.querySelectorAll(selector)];


const api = (method, ...args) => {
    return window.pywebview
        ? pywebview.api[method](...args)
        : Promise.resolve(null);
};


const clamp = (value, min = 0, max = 1) => {
    return Math.max(min, Math.min(max, value));
};


/* ============================================
   CONFIGURATION
============================================ */

const PAGES = [
    "Overview",
    "Processor",
    "Memory",
    "Graphics",
    "Network",
    "Settings"
];


const speed = (bytes) => {

    if (bytes >= 1048576) {
        return (bytes / 1048576).toFixed(2) + " MB/s";
    }

    if (bytes >= 1024) {
        return (bytes / 1024).toFixed(1) + " KB/s";
    }

    return Math.max(bytes, 0).toFixed(0) + " B/s";
};


/* ============================================
   INITIAL UI GENERATION
============================================ */

// Generate performance gauges
$$(".gc").forEach(container => {

    const title = container.dataset.t;
    const gaugeId = container.dataset.g;
    const caption = container.dataset.c;

    container.innerHTML = `
        <div class="h">${title}</div>

        <div class="gauge" data-g="${gaugeId}">
            <svg viewBox="0 0 120 120">

                <circle
                    class="t"
                    cx="60"
                    cy="60"
                    r="46"
                />

                <circle
                    class="a"
                    cx="60"
                    cy="60"
                    r="46"
                    pathLength="100"
                    stroke-dasharray="0 100"
                />

            </svg>

            <b>
                <span>
                    <i>0</i>
                    <small>%</small>
                </span>
            </b>
        </div>

        <div class="cap" style="margin-top:2px">
            ${caption}
        </div>
    `;

});


// Generate information rows
$$("[data-rows]").forEach(container => {

    const [groupId, keys] = container.dataset.rows.split("|");

    container.innerHTML = keys
        .split(",")
        .map(key => {

            return `
                <div>
                    <span>${key}</span>
                    <em data-v="${groupId}.${key}">-</em>
                </div>
            `;

        })
        .join("");

});


// Generate navigation buttons
$("#nav").innerHTML = PAGES.map(page => {

    return `
        <button data-p="${page}">
            <i></i>
            ${page}
        </button>
    `;

}).join("");



/* ============================================
   NAVIGATION
============================================ */

function show(pageName) {

    // Toggle active page
    $$(".page").forEach(page => {

        page.classList.toggle(
            "on",
            page.id === "p-" + pageName
        );

    });


    // Toggle active navigation button
    $$("#nav button").forEach(button => {

        button.classList.toggle(
            "on",
            button.dataset.p === pageName
        );

    });


    // Re-render charts after page changes
    requestAnimationFrame(() => {

        charts.forEach(chart => {
            chart.render(false);
        });

    });

}


$("#nav").onclick = (event) => {

    const button = event.target.closest("button");

    if (!button) return;

    show(button.dataset.p);

};



/* ============================================
   CHART SYSTEM
============================================ */

const HISTORY = 45;
const charts = [];


// Convert Catmull-Rom points into a smooth SVG path
function bezier(points) {

    let path = `M${points[0][0]},${points[0][1]}`;

    for (let i = 0; i < points.length - 1; i++) {

        const previous = points[Math.max(i - 1, 0)];
        const current = points[i];
        const next = points[i + 1];
        const following = points[
            Math.min(i + 2, points.length - 1)
        ];


        path += `
            C${current[0] + (next[0] - previous[0]) / 6},
            ${current[1] + (next[1] - previous[1]) / 6}

            ${next[0] - (following[0] - current[0]) / 6},
            ${next[1] - (following[1] - current[1]) / 6}

            ${next[0]},${next[1]}
        `;

    }

    return path;
}



/* ============================================
   CHART CLASS
============================================ */

class Chart {

    constructor(element, seriesCount, maxValue, formatter) {

        this.el = element;
        this.max = maxValue;
        this.fmt = formatter;

        this.scale = maxValue || 64 * 1024;

        // Create history arrays for each data series
        this.data = Array.from(
            { length: seriesCount },
            () => Array(HISTORY).fill(0)
        );


        // Create SVG chart structure
        element.innerHTML = `
            <svg>

                <g class="grid"></g>

                <g class="series"></g>

                <text x="2" y="10"></text>

            </svg>
        `;


        this.svg = $("svg", element);
        this.series = $(".series", this.svg);


        // Resize chart when its container changes
        new ResizeObserver(() => {
            this.render(false);
        }).observe(element);


        charts.push(this);

    }


    // Add new readings to the chart
    push(...values) {

        values.forEach((value, index) => {

            this.data[index].push(value);
            this.data[index].shift();

        });

        this.render(true);

    }


    // Draw the chart
    render(animate) {

        const width = this.el.clientWidth;
        const height = this.el.clientHeight;

        if (width < 40 || height < 30) return;


        const paddingTop = 6;
        const paddingBottom = 8;

        const usableHeight = height - paddingTop - paddingBottom;

        const spacingX = width / (HISTORY - 2);


        // Calculate chart scale
        const peakValue = Math.max(
            ...this.data.flat(),
            64 * 1024
        ) * 1.25;

        this.scale = this.max || peakValue;


        // Generate horizontal grid lines
        $(".grid", this.svg).innerHTML = [
            0.25,
            0.5,
            0.75
        ].map(position => {

            const y = paddingTop + usableHeight * position;

            return `
                <line
                    class="g"
                    x1="0"
                    x2="${width}"
                    y1="${y}"
                    y2="${y}"
                />
            `;

        }).join("");


        // Update chart scale label
        const label = $("text", this.svg);

        label.setAttribute("x", width - 2);
        label.setAttribute("text-anchor", "end");

        label.textContent = this.fmt(this.scale);


        // Clear previous chart paths
        this.series.innerHTML = "";


        // Draw each data series
        [...this.data.keys()].reverse().forEach(index => {

            const points = this.data[index].map((value, pointIndex) => {

                const x = width -
                    (HISTORY - 1 - pointIndex) * spacingX;

                const y = height -
                    paddingBottom -
                    clamp(value / this.scale) * usableHeight;

                return [x, y];

            });


            const line = bezier(points);
            const opacity = index ? 0.55 : 1;


            this.series.insertAdjacentHTML(
                "beforeend",

                `
                    <g style="opacity:${opacity}">

                        <path
                            class="f"
                            d="${line}L${width},${height}L${points[0][0]},${height}Z"
                        />

                        <path
                            class="l"
                            d="${line}"
                        />

                    </g>
                `
            );

        });


        // Smooth chart animation
        if (
            animate &&
            !matchMedia("(prefers-reduced-motion:reduce)").matches
        ) {

            this.series.animate(

                [
                    {
                        transform: `translateX(${spacingX}px)`
                    },

                    {
                        transform: "translateX(0)"
                    }
                ],

                {
                    duration: 1000,
                    easing: "linear"
                }

            );

        }

    }

}



/* ============================================
   CHART INITIALIZATION
============================================ */

const pct = value => value.toFixed(0) + "%";

const C = {};


$$("[data-chart]").forEach(element => {

    const chartType = element.dataset.chart;

    const seriesCount = chartType === "net" ? 2 : 1;
    const maxValue = chartType === "net" ? 0 : 100;

    const formatter = chartType === "net"
        ? speed
        : pct;


    (C[chartType] = C[chartType] || []).push(

        new Chart(
            element,
            seriesCount,
            maxValue,
            formatter
        )

    );

});



/* ============================================
   LIVE SYSTEM DATA
============================================ */

// Target readings received from Python
const target = {
    cpu: 0,
    mem: 0,
    disk: 0,
    gpu: 0,
    down: 0,
    up: 0
};


// Currently displayed readings
const disp = { ...target };

let lastFrameTime = performance.now();


// Animate values smoothly toward actual readings
function frame(now) {

    const deltaTime = Math.min(
        (now - lastFrameTime) / 1000,
        0.1
    );

    lastFrameTime = now;


    const easing = 1 - Math.exp(-5 * deltaTime);


    // Smoothly interpolate displayed values
    for (const key in disp) {

        disp[key] += (target[key] - disp[key]) * easing;

    }


    // Update performance gauges
    $$(".gauge").forEach(gauge => {

        if (!gauge.offsetParent) return;

        const value = clamp(
            disp[gauge.dataset.g],
            0,
            100
        );


        $(".a", gauge).setAttribute(
            "stroke-dasharray",
            `${value * 0.9999} 100`
        );


        $("i", gauge).textContent = value.toFixed(0);

    });


    // Update network speed displays
    $$("[data-s]").forEach(element => {

        if (!element.offsetParent) return;

        element.textContent = speed(
            disp[element.dataset.s]
        );

    });


    requestAnimationFrame(frame);

}



/* ============================================
   SYSTEM DATA POLLING
============================================ */

let peak = {
    down: 0,
    up: 0
};


async function poll() {

    const stats = await api("stats");


    if (stats) {

        // Update target readings
        for (const key in target) {

            target[key] = stats[key];

        }


        // Track peak network speeds
        peak.down = Math.max(peak.down, stats.down);
        peak.up = Math.max(peak.up, stats.up);


        // Update network charts
        (C.net || []).forEach(chart => {

            chart.push(stats.down, stats.up);

        });


        // Update individual performance charts
        (C.cpu || []).forEach(chart => {
            chart.push(stats.cpu);
        });

        (C.mem || []).forEach(chart => {
            chart.push(stats.mem);
        });

        (C.gpu || []).forEach(chart => {
            chart.push(stats.gpu);
        });


        // Update system information fields
        $$("[data-v]").forEach(element => {

            const value = stats.d[element.dataset.v];

            if (value !== undefined) {
                element.textContent = value;
            }

        });


        // Update network summaries
        $("#dsub").textContent =
            `Total received  ${stats.d["net.recv"]}     Peak  ${speed(peak.down)}`;

        $("#usub").textContent =
            `Total sent  ${stats.d["net.sent"]}     Peak  ${speed(peak.up)}`;


        // Update network interfaces
        $("#ifaces").innerHTML = stats.ifaces
            .map(([name, ip]) => {

                return `
                    <div>
                        <span>${name}</span>
                        <em>${ip}</em>
                    </div>
                `;

            })
            .join("");

    }


    setTimeout(poll, 1000);

}



/* ============================================
   ACCENT COLOR CONFIGURATION
============================================ */

const DEFAULT = "#FFFFFF";
const MINB = 0.35;

const PRESETS = [
    "#FFFFFF",
    "#5CE1FF",
    "#FF4FD8",
    "#7CFF6B",
    "#FFC247",
    "#A78BFA",
    "#FF5C5C"
];


// HSV to HEX conversion
function hsv2hex(hue, saturation, value) {

    const calculateChannel = (n) => {

        const k = (n + hue * 6) % 6;

        return value - value * saturation *
            Math.max(0, Math.min(k, 4 - k, 1));

    };


    const channels = [5, 3, 1].map(channel => {

        return Math.round(calculateChannel(channel) * 255)
            .toString(16)
            .padStart(2, "0");

    });


    return "#" + channels.join("").toUpperCase();

}


// HEX to HSV conversion
function hex2hsv(hex) {

    const [red, green, blue] = [1, 3, 5].map(index => {

        return parseInt(
            hex.slice(index, index + 2),
            16
        ) / 255;

    });


    const max = Math.max(red, green, blue);
    const min = Math.min(red, green, blue);
    const delta = max - min;


    let hue = 0;

    if (delta !== 0) {

        if (max === red) {
            hue = ((green - blue) / delta + 6) % 6;
        }
        else if (max === green) {
            hue = (blue - red) / delta + 2;
        }
        else {
            hue = (red - green) / delta + 4;
        }

    }


    const saturation = max === 0 ? 0 : delta / max;

    return [hue / 6, saturation, max];

}


// Current color state
let savedColor = DEFAULT;

let hue = 0;
let saturation = 0;
let brightness = 1;



/* ============================================
   APPLY ACCENT COLOR
============================================ */

function applyAccent() {

    const hex = hsv2hex(hue, saturation, brightness);
    const root = document.documentElement.style;


    // Update global accent color
    root.setProperty("--accent", hex);


    // Hue slider
    $("#sh").style.setProperty(
        "--g",
        "linear-gradient(90deg,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00)"
    );


    // Saturation slider
    $("#ss").style.setProperty(
        "--g",
        `linear-gradient(
            90deg,
            ${hsv2hex(hue, 0, brightness)},
            ${hsv2hex(hue, 1, brightness)}
        )`
    );


    // Brightness slider
    $("#sb").style.setProperty(
        "--g",
        `linear-gradient(
            90deg,
            ${hsv2hex(hue, saturation, MINB)},
            ${hsv2hex(hue, saturation, 1)}
        )`
    );


    // Update slider positions
    $("#sh").value = hue * 1000;
    $("#ss").value = saturation * 1000;

    $("#sb").value =
        (brightness - MINB) / (1 - MINB) * 1000;


    // Update HEX input and save status
    $("#hex").value = hex;

    $("#status").textContent =
        hex === savedColor
            ? "Saved"
            : "Unsaved changes";


    // Highlight active preset
    $$("#sw button").forEach(button => {

        button.classList.toggle(
            "on",
            button.dataset.c === hex
        );

    });


    return hex;

}



/* ============================================
   SET COLOR FROM HEX
============================================ */

function setHex(hex) {

    const [newHue, newSaturation, newBrightness] = hex2hsv(hex);

    hue = newHue;
    saturation = newSaturation;

    brightness = Math.max(newBrightness, MINB);

    applyAccent();

}



/* ============================================
   COLOR PRESETS
============================================ */

$("#sw").innerHTML = PRESETS.map(color => {

    return `
        <button
            data-c="${color}"
            style="background:${color}"
            aria-label="${color}"
        ></button>
    `;

}).join("");


$("#sw").onclick = (event) => {

    const button = event.target.closest("button");

    if (!button) return;

    setHex(button.dataset.c);

};



/* ============================================
   COLOR SLIDER EVENTS
============================================ */

// Hue
$("#sh").oninput = (event) => {

    hue = event.target.value / 1000;

    applyAccent();

};


// Saturation
$("#ss").oninput = (event) => {

    saturation = event.target.value / 1000;

    applyAccent();

};


// Brightness
$("#sb").oninput = (event) => {

    brightness =
        MINB + (1 - MINB) * event.target.value / 1000;

    applyAccent();

};



/* ============================================
   HEX INPUT EVENTS
============================================ */

$("#hex").onchange = (event) => {

    let hex = event.target.value.trim();

    if (!hex.startsWith("#")) {
        hex = "#" + hex;
    }


    const isValid = /^#[0-9a-f]{6}$/i.test(hex);

    if (isValid) {

        setHex(hex.toUpperCase());

    }
    else {

        $("#status").textContent = "Invalid hex";

    }

};


/* ============================================
   RESET COLOR
============================================ */

$("#reset").onclick = () => {

    setHex(DEFAULT);

};

/* ============================================
   SAVE COLOR
============================================ */

$("#save").onclick = async () => {

    const hex = applyAccent();

    const success = await api("save_accent", hex);


    if (success !== false) {
        savedColor = hex;
    }


    $("#status").textContent =
        success === false
            ? "Couldn't save file"
            : "Saved";

};



/* ============================================
   APPLICATION STARTUP
============================================ */
let booted = false;
async function boot() {
 if (booted) return;
    booted = true;
    // Browser preview only
    if (!window.pywebview) {

        document.documentElement.style.background = "#000";

    }


    // Load saved accent color
    const accent = await api("get_accent");

    savedColor = accent || DEFAULT;

    setHex(savedColor);


    // Open default page
    show("Overview");


    // Start live animations
    requestAnimationFrame(frame);


    // Start system monitoring
    poll();


    // Hide splash screen
    setTimeout(() => {

        $("#splash").classList.add("out");
        $(".app").classList.add("show");

    }, 2300);


    setTimeout(() => {

        $("#splash").remove();

    }, 3200);

}


// Start when PyWebView is ready
window.addEventListener("pywebviewready", boot);


// Allow browser preview without PyWebView
if (!window.pywebview) {

    setTimeout(() => {

        if (!window.pywebview) {
            boot();
        }

    }, 800);

}
