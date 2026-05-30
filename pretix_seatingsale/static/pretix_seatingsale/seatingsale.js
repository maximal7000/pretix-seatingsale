(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== "loading") fn();
        else document.addEventListener("DOMContentLoaded", fn);
    }

    ready(function () {
        var dataEl = document.getElementById("seatingsale-data");
        var catsEl = document.getElementById("seatingsale-cats");
        var svg = document.getElementById("seatingsale-svg");
        if (!dataEl || !svg) return;

        var seats = JSON.parse(dataEl.textContent);
        var cats = JSON.parse(catsEl.textContent);
        var SVGNS = "http://www.w3.org/2000/svg";
        var seatByGuid = {};
        seats.forEach(function (s) { seatByGuid[s.guid] = s; });

        // --- bounds ---
        var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        seats.forEach(function (s) {
            if (s.x < minX) minX = s.x;
            if (s.y < minY) minY = s.y;
            if (s.x > maxX) maxX = s.x;
            if (s.y > maxY) maxY = s.y;
        });
        var pad = 24;
        var w = (maxX - minX) + pad * 2;
        var h = (maxY - minY) + pad * 2;
        svg.setAttribute("viewBox", (minX - pad) + " " + (minY - pad) + " " + w + " " + h);

        // --- legend (only categories that actually have seats) ---
        var usedCats = {};
        seats.forEach(function (s) { usedCats[s.cat] = true; });
        var legend = document.getElementById("seatingsale-legend");
        cats.forEach(function (c) {
            if (!usedCats[c.name]) return;
            var span = document.createElement("span");
            span.className = "seatingsale-legend-item";
            span.innerHTML = '<span class="seatingsale-swatch" style="background:' +
                c.color + '"></span>' + c.name;
            legend.appendChild(span);
        });

        // --- row labels (left edge of each row) ---
        var rows = {};
        seats.forEach(function (s) {
            if (!(s.row in rows) || s.x < rows[s.row].x) {
                rows[s.row] = { x: s.x, y: s.y, label: s.row };
            }
        });
        Object.keys(rows).forEach(function (r) {
            var info = rows[r];
            var t = document.createElementNS(SVGNS, "text");
            t.setAttribute("x", info.x - 16);
            t.setAttribute("y", info.y + 4);
            t.setAttribute("class", "seatingsale-rowlabel");
            t.textContent = info.label;
            svg.appendChild(t);
        });

        // --- selection state (multi) ---
        var selected = {};          // guid -> {seat, circle, variation}
        var circles = {};           // guid -> circle element
        var panel = document.getElementById("seatingsale-panel");
        var list = document.getElementById("seatingsale-list");
        var emptyHint = document.getElementById("seatingsale-empty");
        var counter = document.getElementById("seatingsale-count");
        var form = svg.closest("form");

        function renderList() {
            list.innerHTML = "";
            var guids = Object.keys(selected);
            counter.textContent = guids.length;
            emptyHint.hidden = guids.length > 0;
            panel.hidden = guids.length === 0;

            guids.forEach(function (guid) {
                var entry = selected[guid];
                var seat = entry.seat;
                var prod = seat.product;
                var row = document.createElement("div");
                row.className = "seatingsale-listrow";

                var info = document.createElement("span");
                info.className = "seatingsale-listseat";
                info.innerHTML = '<span class="seatingsale-dot" style="background:' +
                    seat.color + '"></span>' + seat.name;
                row.appendChild(info);

                if (prod.variations && prod.variations.length) {
                    var sel = document.createElement("select");
                    sel.className = "seatingsale-varselect";
                    prod.variations.forEach(function (v) {
                        var o = document.createElement("option");
                        o.value = v.id;
                        o.textContent = v.name + " – " + v.price;
                        if (entry.variation === String(v.id)) o.selected = true;
                        sel.appendChild(o);
                    });
                    entry.variation = sel.value;
                    sel.addEventListener("change", function () {
                        entry.variation = sel.value;
                    });
                    row.appendChild(sel);
                } else {
                    var price = document.createElement("span");
                    price.className = "seatingsale-listprice";
                    price.textContent = prod.price;
                    row.appendChild(price);
                }

                var rm = document.createElement("button");
                rm.type = "button";
                rm.className = "seatingsale-remove";
                rm.setAttribute("aria-label", "remove");
                rm.textContent = "×";
                rm.addEventListener("click", function () {
                    deselect(guid);
                });
                row.appendChild(rm);

                list.appendChild(row);
            });
        }

        function deselect(guid) {
            if (!selected[guid]) return;
            circles[guid].classList.remove("selected");
            delete selected[guid];
            renderList();
        }

        function toggleSeat(seat, circle) {
            if (!seat.available) return;
            if (selected[seat.guid]) {
                deselect(seat.guid);
                return;
            }
            var firstVar = (seat.product.variations && seat.product.variations.length)
                ? String(seat.product.variations[0].id) : null;
            selected[seat.guid] = { seat: seat, circle: circle, variation: firstVar };
            circle.classList.add("selected");
            renderList();
        }

        // --- draw seats with numbers ---
        seats.forEach(function (s) {
            var g = document.createElementNS(SVGNS, "g");
            g.setAttribute("class", "seatingsale-seatg");

            var c = document.createElementNS(SVGNS, "circle");
            c.setAttribute("cx", s.x);
            c.setAttribute("cy", s.y);
            c.setAttribute("r", 11);
            c.setAttribute("fill", s.available ? s.color : "#cccccc");
            c.setAttribute("class", "seatingsale-seat" + (s.available ? "" : " unavailable"));
            var title = document.createElementNS(SVGNS, "title");
            title.textContent = s.name + (s.available ? "" : " ✗");
            c.appendChild(title);

            var num = document.createElementNS(SVGNS, "text");
            num.setAttribute("x", s.x);
            num.setAttribute("y", s.y + 3);
            num.setAttribute("class", "seatingsale-seatnum");
            num.textContent = s.number;

            circles[s.guid] = c;
            if (s.available) {
                g.style.cursor = "pointer";
                g.addEventListener("click", function () { toggleSeat(s, c); });
            }
            g.appendChild(c);
            g.appendChild(num);
            svg.appendChild(g);
        });

        // --- submit: one hidden input per selected seat ---
        function clearHiddenInputs() {
            form.querySelectorAll("input.seatingsale-cart-field").forEach(function (el) {
                el.remove();
            });
        }

        var submitBtn = document.getElementById("seatingsale-submit");
        submitBtn.addEventListener("click", function (ev) {
            var guids = Object.keys(selected);
            if (guids.length === 0) {
                ev.preventDefault();
                return;
            }
            clearHiddenInputs();
            guids.forEach(function (guid) {
                var entry = selected[guid];
                var prod = entry.seat.product;
                var name = "seat_" + prod.item;
                if (entry.variation) name += "_" + entry.variation;
                var inp = document.createElement("input");
                inp.type = "hidden";
                inp.className = "seatingsale-cart-field";
                inp.name = name;
                inp.value = guid;
                form.appendChild(inp);
            });
            // let pretix's data-asynctask handler submit the form
        });
    });
})();
