(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== "loading") {
            fn();
        } else {
            document.addEventListener("DOMContentLoaded", fn);
        }
    }

    ready(function () {
        var root = document.querySelector(".seatingsale");
        if (!root) {
            return;
        }

        var svg = document.getElementById("seatingsale-svg");
        var seatData = JSON.parse(
            document.getElementById("seatingsale-data").textContent
        );
        var catData = JSON.parse(
            document.getElementById("seatingsale-cats").textContent
        );

        var showCategories = root.getAttribute("data-show-categories") === "1";
        var labelRemove = root.getAttribute("data-label-remove") || "Remove";
        var labelMax = root.getAttribute("data-label-max") || "";
        var maxPerOrder = parseInt(root.getAttribute("data-max-per-order"), 10);
        if (isNaN(maxPerOrder) || maxPerOrder < 1) {
            maxPerOrder = 0; // 0 = no limit
        }

        var listEl = document.getElementById("seatingsale-list");
        var emptyEl = document.getElementById("seatingsale-empty");
        var countEl = document.getElementById("seatingsale-count");
        var totalEl = document.getElementById("seatingsale-total");
        var totalValueEl = document.getElementById("seatingsale-total-value");
        var maxHintEl = document.getElementById("seatingsale-maxhint");
        var submitEl = document.getElementById("seatingsale-submit");
        var form = root.closest("form");

        var SVGNS = "http://www.w3.org/2000/svg";

        // guid -> { seat, variation, node }
        var selection = {};
        var nodeByGuid = {};
        var activeFilter = null;

        function firstVariationId(seat) {
            var p = seat.product;
            if (p && p.variations && p.variations.length) {
                return p.variations[0].id;
            }
            return null;
        }

        function variationById(seat, vid) {
            var p = seat.product;
            if (!p || !p.variations) {
                return null;
            }
            for (var i = 0; i < p.variations.length; i++) {
                if (String(p.variations[i].id) === String(vid)) {
                    return p.variations[i];
                }
            }
            return null;
        }

        // ---- geometry ----------------------------------------------------
        var xs = seatData.map(function (s) { return s.x; });
        var ys = seatData.map(function (s) { return s.y; });
        var minX = Math.min.apply(null, xs);
        var maxX = Math.max.apply(null, xs);
        var minY = Math.min.apply(null, ys);
        var maxY = Math.max.apply(null, ys);
        var pad = 20;
        svg.setAttribute(
            "viewBox",
            (minX - pad) + " " + (minY - pad) + " " +
            (maxX - minX + 2 * pad) + " " + (maxY - minY + 2 * pad)
        );

        // ---- row labels --------------------------------------------------
        var rowFirst = {};
        seatData.forEach(function (s) {
            if (!s.row) { return; }
            if (!(s.row in rowFirst) || s.x < rowFirst[s.row].x) {
                rowFirst[s.row] = s;
            }
        });
        Object.keys(rowFirst).forEach(function (row) {
            var s = rowFirst[row];
            var t = document.createElementNS(SVGNS, "text");
            t.setAttribute("x", s.x - 14);
            t.setAttribute("y", s.y);
            t.setAttribute("class", "seatingsale-rowlabel");
            t.textContent = row;
            svg.appendChild(t);
        });

        // ---- seats -------------------------------------------------------
        seatData.forEach(function (s) {
            var g = document.createElementNS(SVGNS, "g");
            g.setAttribute("class", "seatingsale-seat");
            g.setAttribute("data-guid", s.guid);
            g.setAttribute("data-cat", s.cat || "");
            if (!s.available) {
                g.classList.add("seatingsale-seat-taken");
            }

            var circle = document.createElementNS(SVGNS, "circle");
            circle.setAttribute("cx", s.x);
            circle.setAttribute("cy", s.y);
            circle.setAttribute("r", 9);
            circle.setAttribute(
                "fill", s.available ? (s.color || "#3b82f6") : "#cccccc"
            );
            g.appendChild(circle);

            var label = document.createElementNS(SVGNS, "text");
            label.setAttribute("x", s.x);
            label.setAttribute("y", s.y);
            label.setAttribute("class", "seatingsale-seatnum");
            label.textContent = s.number || "";
            g.appendChild(label);

            var title = document.createElementNS(SVGNS, "title");
            title.textContent = s.name || "";
            g.appendChild(title);

            nodeByGuid[s.guid] = { node: g, seat: s };

            if (s.available) {
                g.addEventListener("click", function () {
                    toggleSeat(s, g);
                });
            }
            svg.appendChild(g);
        });

        // ---- category legend / filter ------------------------------------
        if (showCategories) {
            var legend = document.getElementById("seatingsale-legend");
            catData.forEach(function (c) {
                var item = document.createElement("button");
                item.type = "button";
                item.className = "seatingsale-legenditem";
                item.setAttribute("data-cat", c.name);

                var sw = document.createElement("span");
                sw.className = "seatingsale-swatch";
                sw.style.background = c.color || "#3b82f6";
                item.appendChild(sw);

                var lbl = document.createElement("span");
                lbl.textContent = c.name;
                item.appendChild(lbl);

                item.addEventListener("click", function () {
                    activeFilter = (activeFilter === c.name) ? null : c.name;
                    applyFilter();
                });
                legend.appendChild(item);
            });
        }

        function applyFilter() {
            Object.keys(nodeByGuid).forEach(function (guid) {
                var entry = nodeByGuid[guid];
                var dim = activeFilter && entry.seat.cat !== activeFilter;
                entry.node.classList.toggle("seatingsale-dim", !!dim);
            });
            if (showCategories) {
                var items = document.querySelectorAll(".seatingsale-legenditem");
                Array.prototype.forEach.call(items, function (el) {
                    el.classList.toggle(
                        "active", el.getAttribute("data-cat") === activeFilter
                    );
                });
            }
        }

        // ---- selection ---------------------------------------------------
        function selectedCount() {
            return Object.keys(selection).length;
        }

        function atLimit() {
            return maxPerOrder > 0 && selectedCount() >= maxPerOrder;
        }

        function toggleSeat(seat, node) {
            if (selection[seat.guid]) {
                deselect(seat.guid);
                return;
            }
            if (atLimit()) {
                showMaxHint();
                return;
            }
            selection[seat.guid] = {
                seat: seat,
                variation: firstVariationId(seat),
                node: node
            };
            node.classList.add("seatingsale-selected");
            render();
        }

        function deselect(guid) {
            var entry = selection[guid];
            if (!entry) { return; }
            entry.node.classList.remove("seatingsale-selected");
            delete selection[guid];
            render();
        }

        var maxHintTimer = null;
        function showMaxHint() {
            if (!maxHintEl || !labelMax) { return; }
            maxHintEl.textContent = labelMax;
            maxHintEl.hidden = false;
            if (maxHintTimer) { clearTimeout(maxHintTimer); }
            maxHintTimer = setTimeout(function () {
                maxHintEl.hidden = true;
            }, 4000);
        }

        function priceOf(entry) {
            var v = variationById(entry.seat, entry.variation);
            if (v) {
                return parseFloat(v.price) || 0;
            }
            var p = entry.seat.product;
            return p ? (parseFloat(p.price) || 0) : 0;
        }

        function priceLabel(entry) {
            var v = variationById(entry.seat, entry.variation);
            if (v) {
                return v.price;
            }
            var p = entry.seat.product;
            return p ? p.price : "";
        }

        function render() {
            var guids = Object.keys(selection);
            countEl.textContent = guids.length;

            listEl.innerHTML = "";
            var total = 0;

            guids.forEach(function (guid) {
                var entry = selection[guid];
                var seat = entry.seat;
                var product = seat.product;
                total += priceOf(entry);

                var card = document.createElement("div");
                card.className = "seatingsale-card";

                var dot = document.createElement("span");
                dot.className = "seatingsale-carddot";
                dot.style.background = seat.color || "#3b82f6";
                card.appendChild(dot);

                var info = document.createElement("div");
                info.className = "seatingsale-cardinfo";

                var name = document.createElement("div");
                name.className = "seatingsale-cardname";
                name.textContent = seat.name || "";
                info.appendChild(name);

                if (product && product.variations && product.variations.length > 1) {
                    var sel = document.createElement("select");
                    sel.className = "seatingsale-cardselect form-control input-sm";
                    product.variations.forEach(function (v) {
                        var opt = document.createElement("option");
                        opt.value = v.id;
                        opt.textContent = v.name + " · " + v.price;
                        if (String(v.id) === String(entry.variation)) {
                            opt.selected = true;
                        }
                        sel.appendChild(opt);
                    });
                    sel.addEventListener("change", function () {
                        entry.variation = sel.value;
                        render();
                    });
                    info.appendChild(sel);
                } else {
                    var price = document.createElement("div");
                    price.className = "seatingsale-cardprice";
                    if (product && product.variations && product.variations.length === 1) {
                        price.textContent = product.variations[0].name +
                            " · " + product.variations[0].price;
                    } else {
                        price.textContent = priceLabel(entry);
                    }
                    info.appendChild(price);
                }
                card.appendChild(info);

                var rm = document.createElement("button");
                rm.type = "button";
                rm.className = "seatingsale-cardremove";
                rm.setAttribute("aria-label", labelRemove);
                rm.title = labelRemove;
                rm.innerHTML = "&times;";
                rm.addEventListener("click", function () {
                    deselect(guid);
                });
                card.appendChild(rm);

                listEl.appendChild(card);
            });

            emptyEl.hidden = guids.length > 0;
            if (guids.length > 0) {
                totalEl.hidden = false;
                totalValueEl.textContent = total.toFixed(2);
            } else {
                totalEl.hidden = true;
            }
            submitEl.disabled = guids.length === 0;

            if (maxHintEl && !atLimit()) {
                maxHintEl.hidden = true;
            }
        }

        // ---- submit ------------------------------------------------------
        // Inject one hidden field per selected seat on button click, before
        // pretix' data-asynctask handler serialises the form.
        submitEl.addEventListener("click", function (ev) {
            var guids = Object.keys(selection);
            if (guids.length === 0) {
                ev.preventDefault();
                return;
            }
            var old = form.querySelectorAll(".seatingsale-cartfield");
            Array.prototype.forEach.call(old, function (el) {
                el.parentNode.removeChild(el);
            });
            guids.forEach(function (guid) {
                var entry = selection[guid];
                var name = "seat_" + entry.seat.product.item;
                if (entry.variation) {
                    name += "_" + entry.variation;
                }
                var inp = document.createElement("input");
                inp.type = "hidden";
                inp.className = "seatingsale-cartfield";
                inp.name = name;
                inp.value = guid;
                form.appendChild(inp);
            });
            // let pretix' data-asynctask handler submit the form
        });

        render();
    });
})();
