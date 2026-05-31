(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== "loading") fn();
        else document.addEventListener("DOMContentLoaded", fn);
    }

    ready(function () {
        var root = document.querySelector(".seatingsale");
        var dataEl = document.getElementById("seatingsale-data");
        var catsEl = document.getElementById("seatingsale-cats");
        var svg = document.getElementById("seatingsale-svg");
        if (!root || !dataEl || !svg) return;

        var seats = JSON.parse(dataEl.textContent);
        var cats = JSON.parse(catsEl.textContent);
        var showCategories = root.getAttribute("data-show-categories") === "1";
        var labelRemove = root.getAttribute("data-label-remove") || "Remove";
        var SVGNS = "http://www.w3.org/2000/svg";

        // --- bounds ---
        var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        seats.forEach(function (s) {
            if (s.x < minX) minX = s.x;
            if (s.y < minY) minY = s.y;
            if (s.x > maxX) maxX = s.x;
            if (s.y > maxY) maxY = s.y;
        });
        var pad = 24;
        svg.setAttribute("viewBox", (minX - pad) + " " + (minY - pad) + " " +
            ((maxX - minX) + pad * 2) + " " + ((maxY - minY) + pad * 2));

        // --- state ---
        var selected = {};      // guid -> {seat, variation}
        var circles = {};       // guid -> circle element
        var activeFilter = null; // category name, or null = show all

        var list = document.getElementById("seatingsale-list");
        var emptyHint = document.getElementById("seatingsale-empty");
        var counter = document.getElementById("seatingsale-count");
        var totalBox = document.getElementById("seatingsale-total");
        var totalVal = document.getElementById("seatingsale-total-value");
        var submitBtn = document.getElementById("seatingsale-submit");
        var form = svg.closest("form");

        function parsePrice(p) {
            var n = parseFloat(String(p).replace(",", "."));
            return isNaN(n) ? 0 : n;
        }

        function priceOf(entry) {
            var prod = entry.seat.product;
            if (prod.variations && prod.variations.length) {
                for (var i = 0; i < prod.variations.length; i++) {
                    if (String(prod.variations[i].id) === String(entry.variation)) {
                        return parsePrice(prod.variations[i].price);
                    }
                }
            }
            return parsePrice(prod.price);
        }

        // --- category legend / filter ---
        if (showCategories) {
            var legend = document.getElementById("seatingsale-legend");
            cats.forEach(function (c) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "seatingsale-legend-item";
                btn.dataset.cat = c.name;
                btn.innerHTML = '<span class="seatingsale-swatch" style="background:' +
                    c.color + '"></span>' + c.name;
                btn.addEventListener("click", function () {
                    activeFilter = (activeFilter === c.name) ? null : c.name;
                    applyFilter();
                });
                legend.appendChild(btn);
            });
        }

        function applyFilter() {
            if (showCategories) {
                var items = document.querySelectorAll(".seatingsale-legend-item");
                items.forEach(function (el) {
                    el.classList.toggle("active", el.dataset.cat === activeFilter);
                });
            }
            seats.forEach(function (s) {
                var g = circles[s.guid].parentNode;
                var dim = activeFilter && s.cat !== activeFilter;
                g.classList.toggle("dimmed", !!dim);
            });
        }

        // --- row labels ---
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

        // --- selection rendering ---
        function renderList() {
            list.innerHTML = "";
            var guids = Object.keys(selected);
            counter.textContent = guids.length;
            emptyHint.hidden = guids.length > 0;
            submitBtn.disabled = guids.length === 0;

            var total = 0;
            guids.forEach(function (guid) {
                var entry = selected[guid];
                var seat = entry.seat;
                var prod = seat.product;

                var card = document.createElement("div");
                card.className = "seatingsale-card";

                var top = document.createElement("div");
                top.className = "seatingsale-card-top";
                top.innerHTML = '<span class="seatingsale-dot" style="background:' +
                    seat.color + '"></span>' +
                    '<span class="seatingsale-card-name">' + seat.name + "</span>";

                var rm = document.createElement("button");
                rm.type = "button";
                rm.className = "seatingsale-remove";
                rm.setAttribute("aria-label", labelRemove);
                rm.textContent = "×";
                rm.addEventListener("click", function () { deselect(guid); });
                top.appendChild(rm);
                card.appendChild(top);

                var bottom = document.createElement("div");
                bottom.className = "seatingsale-card-bottom";
                if (prod.variations && prod.variations.length) {
                    var sel = document.createElement("select");
                    sel.className = "seatingsale-varselect form-control input-sm";
                    prod.variations.forEach(function (v) {
                        var o = document.createElement("option");
                        o.value = v.id;
                        o.textContent = v.name + " · " + v.price;
                        if (String(entry.variation) === String(v.id)) o.selected = true;
                        sel.appendChild(o);
                    });
                    entry.variation = sel.value;
                    sel.addEventListener("change", function () {
                        entry.variation = sel.value;
                        renderList();
                    });
                    bottom.appendChild(sel);
                } else {
                    var price = document.createElement("span");
                    price.className = "seatingsale-card-price";
                    price.textContent = prod.price;
                    bottom.appendChild(price);
                }
                card.appendChild(bottom);
                list.appendChild(card);

                total += priceOf(entry);
            });

            if (guids.length > 0) {
                totalBox.hidden = false;
                totalVal.textContent = total.toFixed(2).replace(".", ",");
            } else {
                totalBox.hidden = true;
            }
        }

        function deselect(guid) {
            if (!selected[guid]) return;
            circles[guid].classList.remove("selected");
            delete selected[guid];
            renderList();
        }

        function toggleSeat(seat) {
            if (!seat.available) return;
            if (selected[seat.guid]) {
                deselect(seat.guid);
                return;
            }
            var firstVar = (seat.product.variations && seat.product.variations.length)
                ? String(seat.product.variations[0].id) : null;
            selected[seat.guid] = { seat: seat, variation: firstVar };
            circles[seat.guid].classList.add("selected");
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
                g.addEventListener("click", function () { toggleSeat(s); });
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

        renderList();
    });
})();
